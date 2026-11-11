"""services/payment.py そのもののテスト。本物の Stripe は呼ばず、_client を差し替える。"""

import time
from types import SimpleNamespace

import pytest
import stripe
from helpers import make_order, make_product

from marche.services import payment
from marche.services.payment import PaymentError


class FakeSessions:
    """client.v1.checkout.sessions の代わり。渡された引数を記録する"""

    def __init__(self):
        self.error = None
        self.create_params = None
        self.retrieved = []
        self.expired = []

    def create(self, params):
        if self.error:
            raise self.error
        self.create_params = params
        return SimpleNamespace(id="cs_test_abc", url="https://checkout.stripe.test/abc")

    def retrieve(self, session_id):
        if self.error:
            raise self.error
        self.retrieved.append(session_id)
        return SimpleNamespace(id=session_id, payment_status="paid")

    def expire(self, session_id):
        if self.error:
            raise self.error
        self.expired.append(session_id)


@pytest.fixture
def sessions(monkeypatch):
    sessions = FakeSessions()
    client = SimpleNamespace(
        v1=SimpleNamespace(checkout=SimpleNamespace(sessions=sessions))
    )
    monkeypatch.setattr(payment, "_client", lambda: client)
    return sessions


@pytest.fixture
def order(customer, producer):
    a = make_product(producer, name="ほうれん草 1束", price=300)
    b = make_product(producer, name="高原トマト 500g", price=600)
    return make_order(customer, [(a, 2), (b, 1)])


def create(app, order):
    with app.test_request_context():
        return payment.create_checkout_session(order)


def test_Checkout_Sessionを作ってIDとURLを返す(app, sessions, order):
    assert create(app, order) == ("cs_test_abc", "https://checkout.stripe.test/abc")


def test_line_itemsは明細の単価と商品名と数量(app, sessions, order):
    create(app, order)
    params = sessions.create_params
    assert params["mode"] == "payment"
    assert params["line_items"] == [
        {
            "quantity": 2,
            "price_data": {
                "currency": "jpy",
                "unit_amount": 300,  # 円のまま（100倍しない）
                "product_data": {"name": "ほうれん草 1束"},
            },
        },
        {
            "quantity": 1,
            "price_data": {
                "currency": "jpy",
                "unit_amount": 600,
                "product_data": {"name": "高原トマト 500g"},
            },
        },
    ]


def test_金額は注文の明細から取り商品の今の価格は使わない(app, sessions, order):
    order.items[0].product.price = 9999
    create(app, order)
    assert sessions.create_params["line_items"][0]["price_data"]["unit_amount"] == 300


def test_metadataに注文IDが入る(app, sessions, order):
    create(app, order)
    assert sessions.create_params["metadata"] == {"order_id": str(order.id)}


def test_購入者のメールアドレスを渡す(app, sessions, order):
    create(app, order)
    assert sessions.create_params["customer_email"] == "customer@example.com"


def test_成功と中断のURLは自サイトの絶対URL(app, sessions, order):
    create(app, order)
    params = sessions.create_params
    # {CHECKOUT_SESSION_ID} は Stripe が置き換えるので、そのまま残す
    assert params["success_url"] == (
        f"http://localhost/orders/{order.id}/complete?session_id={{CHECKOUT_SESSION_ID}}"
    )
    assert params["cancel_url"] == f"http://localhost/orders/{order.id}/cancel"


def test_有効期限は31分後(app, sessions, order):
    before = int(time.time())
    create(app, order)
    expires_at = sessions.create_params["expires_at"]
    assert before + 31 * 60 <= expires_at <= int(time.time()) + 31 * 60


def test_StripeErrorはPaymentErrorになる(app, sessions, order):
    sessions.error = stripe.StripeError("boom")
    with pytest.raises(PaymentError) as info:
        create(app, order)
    assert "決済ページを作れませんでした" in str(info.value)
    assert isinstance(info.value.__cause__, stripe.StripeError)


def test_キーが設定されていないとPaymentError(app, order):
    app.config["STRIPE_SECRET_KEY"] = ""
    with pytest.raises(PaymentError) as info:
        create(app, order)
    assert "設定" in str(info.value)


def test_retrieve_sessionはSessionを取得する(app, sessions):
    with app.app_context():
        session = payment.retrieve_session("cs_test_abc")
    assert session.payment_status == "paid"
    assert sessions.retrieved == ["cs_test_abc"]


def test_retrieve_sessionの失敗はPaymentError(app, sessions):
    sessions.error = stripe.APIConnectionError("down")
    with app.app_context(), pytest.raises(PaymentError):
        payment.retrieve_session("cs_test_abc")


def test_expire_sessionはSessionを期限切れにする(app, sessions):
    with app.app_context():
        payment.expire_session("cs_test_abc")
    assert sessions.expired == ["cs_test_abc"]


def test_expire_sessionの失敗はPaymentError(app, sessions):
    sessions.error = stripe.InvalidRequestError("already paid", param=None)
    with app.app_context(), pytest.raises(PaymentError):
        payment.expire_session("cs_test_abc")


def test_ビューが使うのは設定で渡したフェイク(app, fake_payment):
    assert app.extensions["payment"] is fake_payment


def test_設定がなければ本物のモジュールが入る():
    from marche import create_app

    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert app.extensions["payment"] is payment
