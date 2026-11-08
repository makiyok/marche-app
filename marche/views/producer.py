from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user

from marche.decorators import role_required
from marche.extensions import db
from marche.forms import ProductForm
from marche.models import Product, Role
from marche.uploads import delete_image, detect_media_type, save_image

bp = Blueprint("producer", __name__, url_prefix="/producer")

IMAGE_ERROR = "JPEG・PNG・WebP の画像を選んでください"


def get_own_product_or_403(product_id: int) -> Product:
    """自分の商品を返す。商品がなければ 404、他の生産者の商品なら 403"""
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)
    if product.producer_id != current_user.id:
        abort(403)
    return product


def read_image(form: ProductForm) -> tuple[bytes, str] | None:
    """選ばれた写真を読み、中身を確かめる。選ばれていなければ None。
    画像でなければ、フォームにエラーを足して ValueError にする"""
    file = form.image.data
    if not file or not file.filename:
        return None
    data = file.read()
    media_type = detect_media_type(data)
    if media_type is None:
        form.image.errors.append(IMAGE_ERROR)
        raise ValueError(IMAGE_ERROR)
    return data, media_type


def render_form(form: ProductForm, product: Product | None, status: int):
    return render_template("producer/form.html", form=form, product=product), status


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
        try:
            image = read_image(form)
        except ValueError:
            return render_form(form, None, 422)
        filename = save_image(*image) if image else None
        product = Product(
            producer_id=current_user.id,  # フォームからは受け取らない
            name=form.name.data.strip(),
            description=form.description.data or "",
            price=form.price.data,
            stock=form.stock.data,
            is_published=form.is_published.data,
            image_filename=filename,
        )
        try:
            db.session.add(product)
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_image(filename)  # 保存できなかった商品の写真を残さない
            raise
        flash("商品を登録しました")
        return redirect(url_for("producer.index"))
    return render_form(form, None, 422 if form.is_submitted() else 200)


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@role_required(Role.PRODUCER)
def edit(product_id):
    product = get_own_product_or_403(product_id)
    form = ProductForm(obj=product)
    if form.validate_on_submit():
        try:
            image = read_image(form)
        except ValueError:
            return render_form(form, product, 422)
        old_filename = product.image_filename
        new_filename = save_image(*image) if image else None
        product.name = form.name.data.strip()
        product.description = form.description.data or ""
        product.price = form.price.data
        product.stock = form.stock.data
        product.is_published = form.is_published.data
        if new_filename:
            product.image_filename = new_filename
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_image(new_filename)
            raise
        if new_filename:
            delete_image(old_filename)  # 保存に成功してから、古い写真を消す
        flash("商品を更新しました")
        return redirect(url_for("producer.index"))
    return render_form(form, product, 422 if form.is_submitted() else 200)


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
    filename = product.image_filename
    db.session.delete(product)
    db.session.commit()
    delete_image(filename)  # 商品を消せてから、写真を消す
    flash("商品を削除しました")
    return redirect(url_for("producer.index"))
