from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from marche.cart import clear_cart, get_cart
from marche.extensions import db
from marche.models import Order, OrderStatus
from marche.services import inventory
from marche.services.orders import OrderError, create_order
from marche.services.payment import PaymentError
from marche.views.cart import render_cart

bp = Blueprint("orders", __name__, url_prefix="/orders")


def get_own_order_or_403(order_id: int) -> Order:
    """注文を返す。なければ 404、注文した本人と管理者以外は 403"""
    order = db.session.get(Order, order_id)
    if order is None:
        abort(404)
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return order


@bp.route("/", methods=["POST"])
def create():
    # POST だけの URL なので、ログインしたあとはカートへ戻す
    if not current_user.is_authenticated:
        flash("ログインしてください")
        return redirect(url_for("auth.login", next=url_for("cart.index")))
    try:
        order = create_order(current_user, get_cart())
    except OrderError as error:
        flash(str(error))
        return render_cart(422)

    # 外部サービスは、current_app.extensions 経由で呼ぶ（テストではフェイクに差し替わる）
    payment = current_app.extensions["payment"]
    try:
        session_id, url = payment.create_checkout_session(order)
    except PaymentError as error:
        # 決済ページを作れなかった注文は、取り消してカートに戻す（カートは残したまま）
        inventory.cancel(order)
        flash(str(error))
        return render_cart(422)

    order.stripe_checkout_session_id = session_id
    db.session.commit()
    clear_cart()
    return redirect(url, 303)


@bp.route("/<int:order_id>")
@login_required
def detail(order_id):
    order = get_own_order_or_403(order_id)
    return render_template("orders/detail.html", order=order)


@bp.route("/<int:order_id>/complete")
@login_required
def complete(order_id):
    # 仮の画面。支払いの確認（Stripe への問い合わせ）は、あとの章で作る
    order = get_own_order_or_403(order_id)
    return render_template("orders/complete.html", order=order)


@bp.route("/<int:order_id>/cancel", methods=["GET", "POST"])
@login_required
def cancel(order_id):
    order = get_own_order_or_403(order_id)
    if request.method == "GET":
        return render_template("orders/cancel.html", order=order)

    if order.status != OrderStatus.PENDING:
        flash("この注文は取り消せません")
        return redirect(url_for("orders.detail", order_id=order.id))

    # 先に決済ページを期限切れにする。できなかったら、取り消さずに注文詳細へ
    # （期限切れにできない＝すでに支払いが済んでいるかもしれないため）
    if order.stripe_checkout_session_id:
        payment = current_app.extensions["payment"]
        try:
            payment.expire_session(order.stripe_checkout_session_id)
        except PaymentError as error:
            flash(f"{error}（注文は取り消していません）")
            return redirect(url_for("orders.detail", order_id=order.id))

    if inventory.cancel(order):
        flash("注文を取り消しました")
    else:
        flash("この注文は取り消せません")
    return redirect(url_for("orders.detail", order_id=order.id))
