from flask import Blueprint, render_template
from sqlalchemy.orm import joinedload

from marche.extensions import db
from marche.models import Product

bp = Blueprint("shop", __name__)


@bp.route("/")
def index():
    # 公開中の商品だけを、新しい順に出す。生産者名も出すので、まとめて取得する
    products = db.session.scalars(
        db.select(Product)
        .filter_by(is_published=True)
        .options(joinedload(Product.producer))
        .order_by(Product.id.desc())
    ).all()
    return render_template("shop/index.html", products=products)
