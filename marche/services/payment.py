"""Stripe（Checkout）を呼ぶのは、このファイルだけ。

ビューは `current_app.extensions["payment"]` 経由で呼ぶ。テストではフェイクに差し替える。
"""

import logging
import time

import stripe
from flask import current_app, url_for

from marche.models import Order

logger = logging.getLogger(__name__)

# Checkout Session の有効期限（分）。Stripe の最短は30分なので、時計のずれを見込んで31分にする
SESSION_MINUTES = 31


class PaymentError(Exception):
    """決済サービスの失敗。メッセージは、そのまま画面に出せる日本語"""


def _client() -> stripe.StripeClient:
    key = current_app.config["STRIPE_SECRET_KEY"]
    if not key:
        raise PaymentError("決済の設定がされていません")
    return stripe.StripeClient(key)


def create_checkout_session(order: Order) -> tuple[str, str]:
    """Checkout Session を作り、(session_id, 決済ページの URL) を返す。

    金額・商品名は、注文の明細（データベースの値）から取る。
    JPY は小数のない通貨なので、unit_amount は円のまま（100倍しない）。
    """
    client = _client()
    params = {
        "mode": "payment",
        "line_items": [
            {
                "quantity": item.quantity,
                "price_data": {
                    "currency": "jpy",
                    "unit_amount": item.unit_price,
                    "product_data": {"name": item.product_name},
                },
            }
            for item in order.items
        ],
        "customer_email": order.user.email,
        "metadata": {"order_id": str(order.id)},
        # {CHECKOUT_SESSION_ID} は、Stripe が Session の ID に置き換える
        "success_url": url_for("orders.complete", order_id=order.id, _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": url_for("orders.cancel", order_id=order.id, _external=True),
        "expires_at": int(time.time()) + SESSION_MINUTES * 60,
    }
    try:
        session = client.v1.checkout.sessions.create(params)
    except stripe.StripeError as error:
        logger.exception("Checkout Session を作れませんでした（注文 %s）", order.id)
        raise PaymentError(
            "決済ページを作れませんでした。時間をおいて、もう一度お試しください"
        ) from error
    return session.id, session.url


def retrieve_session(session_id: str):
    """Checkout Session を取得する（完了ページで、支払い済みかを確かめるときに使う）"""
    client = _client()
    try:
        return client.v1.checkout.sessions.retrieve(session_id)
    except stripe.StripeError as error:
        logger.exception("Checkout Session を取得できませんでした（%s）", session_id)
        raise PaymentError(
            "支払いの状態を確認できませんでした。時間をおいて、もう一度お試しください"
        ) from error


def expire_session(session_id: str) -> None:
    """Checkout Session を期限切れにする（注文を取り消す前に使う）"""
    client = _client()
    try:
        client.v1.checkout.sessions.expire(session_id)
    except stripe.StripeError as error:
        logger.exception(
            "Checkout Session を期限切れにできませんでした（%s）", session_id
        )
        raise PaymentError(
            "決済ページを閉じられませんでした。時間をおいて、もう一度お試しください"
        ) from error
