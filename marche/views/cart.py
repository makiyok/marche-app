from flask import Blueprint, abort, flash, redirect, render_template, url_for

from marche.cart import cart_lines, get_cart, save_cart
from marche.forms import AddToCartForm, CartUpdateForm
from marche.services.inventory import available_stock
from marche.services.orders import MAX_QUANTITY
from marche.views.shop import published_product_or_404, quantity_choices, render_detail

bp = Blueprint("cart", __name__, url_prefix="/cart")


def render_cart(status: int = 200):
    cart = get_cart()
    lines = cart_lines(cart)
    # 非公開になった商品・消えた商品は、セッションからも外す
    if len(lines) != len(cart):
        save_cart({product.id: quantity for product, quantity in lines})
    total = sum(product.price * quantity for product, quantity in lines)  # 表示用
    return (
        render_template("cart/index.html", lines=lines, total=total),
        status,
    )


@bp.route("/")
def index():
    return render_cart()


@bp.route("/add/<int:product_id>", methods=["POST"])
def add(product_id):
    product = published_product_or_404(product_id)
    form = AddToCartForm()
    available = available_stock(product)
    form.quantity.choices = quantity_choices(available)
    if form.validate_on_submit():
        cart = get_cart()
        limit = min(MAX_QUANTITY, available)
        new_quantity = cart.get(product.id, 0) + form.quantity.data
        if not 1 <= form.quantity.data <= limit:
            form.quantity.errors.append("数量を選び直してください")
        elif new_quantity > limit:
            form.quantity.errors.append(
                f"カートに入れられるのは、あと{max(limit - cart.get(product.id, 0), 0)}個までです"
            )
        else:
            cart[product.id] = new_quantity
            save_cart(cart)
            flash(f"{product.name}をカートに入れました")
            return redirect(url_for("cart.index"))
    elif form.quantity.errors:
        form.quantity.errors = ["数量を選び直してください"]
    return render_detail(product, form, 422)


@bp.route("/update/<int:product_id>", methods=["POST"])
def update(product_id):
    product = published_product_or_404(product_id)
    cart = get_cart()
    if product.id not in cart:
        abort(404)
    form = CartUpdateForm()
    if form.validate_on_submit():
        quantity = form.quantity.data
        limit = min(MAX_QUANTITY, available_stock(product))
        if quantity == 0:
            del cart[product.id]
            save_cart(cart)
            flash(f"{product.name}をカートから外しました")
            return redirect(url_for("cart.index"))
        if quantity <= limit:
            cart[product.id] = quantity
            save_cart(cart)
            flash("数量を変えました")
            return redirect(url_for("cart.index"))
        flash(f"{product.name}は、あと{limit}個までです")
    else:
        flash("数量は 0〜10 で入力してください")
    return render_cart(422)
