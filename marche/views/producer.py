from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user

from marche.decorators import role_required
from marche.extensions import db
from marche.forms import ProductForm
from marche.models import Product, Role

bp = Blueprint("producer", __name__, url_prefix="/producer")


def get_own_product_or_403(product_id: int) -> Product:
    """自分の商品を返す。商品がなければ 404、他の生産者の商品なら 403"""
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)
    if product.producer_id != current_user.id:
        abort(403)
    return product


@bp.route("/products")
@role_required(Role.PRODUCER)
def index():
    products = db.session.scalars(
        db.select(Product)
        .filter_by(producer_id=current_user.id)
        .order_by(Product.id.desc())
    ).all()
    return render_template("producer/index.html", products=products)


@bp.route("/products/new", methods=["GET", "POST"])
@role_required(Role.PRODUCER)
def new():
    form = ProductForm()
    if form.validate_on_submit():
        product = Product(
            producer_id=current_user.id,  # フォームからは受け取らない
            name=form.name.data.strip(),
            description=form.description.data or "",
            price=form.price.data,
            stock=form.stock.data,
            is_published=form.is_published.data,
        )
        db.session.add(product)
        db.session.commit()
        flash("商品を登録しました")
        return redirect(url_for("producer.index"))
    status = 422 if form.is_submitted() else 200
    return render_template("producer/form.html", form=form, product=None), status


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@role_required(Role.PRODUCER)
def edit(product_id):
    product = get_own_product_or_403(product_id)
    form = ProductForm(obj=product)
    if form.validate_on_submit():
        product.name = form.name.data.strip()
        product.description = form.description.data or ""
        product.price = form.price.data
        product.stock = form.stock.data
        product.is_published = form.is_published.data
        db.session.commit()
        flash("商品を更新しました")
        return redirect(url_for("producer.index"))
    status = 422 if form.is_submitted() else 200
    return render_template("producer/form.html", form=form, product=product), status


@bp.route("/products/<int:product_id>/toggle", methods=["POST"])
@role_required(Role.PRODUCER)
def toggle(product_id):
    product = get_own_product_or_403(product_id)
    product.is_published = not product.is_published
    db.session.commit()
    flash("公開しました" if product.is_published else "非公開にしました")
    return redirect(url_for("producer.index"))


@bp.route("/products/<int:product_id>/delete", methods=["POST"])
@role_required(Role.PRODUCER)
def delete(product_id):
    # 注文がある商品は削除できない、という確認は、注文の機能を作るときに足す
    product = get_own_product_or_403(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("商品を削除しました")
    return redirect(url_for("producer.index"))
