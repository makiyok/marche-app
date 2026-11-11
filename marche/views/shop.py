from flask import Blueprint, abort, render_template
from flask_login import current_user
from sqlalchemy.orm import joinedload

from marche.extensions import db
from marche.forms import AddToCartForm
from marche.models import Product
from marche.services.inventory import available_stock
from marche.services.orders import MAX_QUANTITY

bp = Blueprint("shop", __name__)


def published_product_or_404(product_id: int) -> Product:
    """公開中の商品を返す。存在しない・非公開なら 404"""
    product = db.session.get(Product, product_id)
    if product is None or not product.is_published:
        abort(404)
    return product


def can_view(product: Product) -> bool:
    """非公開の商品を見られるのは、出品した生産者と管理者だけ"""
    return current_user.is_authenticated and (
        current_user.is_admin or product.producer_id == current_user.id
    )


def quantity_choices(available: int) -> list[tuple[int, str]]:
    """数量のセレクトの選択肢。1〜min(10, いま買える数)"""
    return [(n, str(n)) for n in range(1, min(MAX_QUANTITY, available) + 1)]


def render_detail(product: Product, form: AddToCartForm, status: int = 200):
    available = available_stock(product)
    form.quantity.choices = quantity_choices(available)
    return (
        render_template(
            "shop/detail.html", product=product, form=form, available=available
        ),
        status,
    )


@bp.route("/")
def index():
    # 公開中の商品だけを、新しい順に出す。生産者名も出すので、まとめて取得する
    products = db.session.scalars(
        db.select(Product)
        .filter_by(is_published=True)
        .options(joinedload(Product.producer))
        .order_by(Product.id.desc())
    ).all()
    # 在庫は「いま買える数」（支払い待ちの分を引いた数）を出す
    items = [(product, available_stock(product)) for product in products]
    return render_template("shop/index.html", items=items)


@bp.route("/products/<int:product_id>")
def detail(product_id):
    product = db.session.get(Product, product_id)
    # 非公開の商品は、見られない人には「ある」ことも教えない（404）
    if product is None or (not product.is_published and not can_view(product)):
        abort(404)
    return render_detail(product, AddToCartForm())
