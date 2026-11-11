from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from marche.cart import clear_cart, get_cart
from marche.extensions import db
from marche.models import Order
from marche.services.orders import OrderError, create_order
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
    clear_cart()
    flash("ご注文を受け付けました")
    return redirect(url_for("orders.detail", order_id=order.id), 303)


@bp.route("/<int:order_id>")
@login_required
def detail(order_id):
    order = get_own_order_or_403(order_id)
    return render_template("orders/detail.html", order=order)
