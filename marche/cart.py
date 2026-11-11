"""カート。セッションに {"商品ID": 数量} で持つ（テーブルは作らない）"""

from flask import session

from marche.extensions import db
from marche.models import Product

SESSION_KEY = "cart"


def get_cart() -> dict[int, int]:
    """セッションのカートを {商品ID: 数量} で返す。壊れた値は捨てる"""
    cart = {}
    for key, value in (session.get(SESSION_KEY) or {}).items():
        try:
            product_id, quantity = int(key), int(value)
        except TypeError, ValueError:
            continue
        if quantity > 0:
            cart[product_id] = quantity
    return cart


def save_cart(cart: dict[int, int]) -> None:
    session[SESSION_KEY] = {str(product_id): q for product_id, q in cart.items()}


def clear_cart() -> None:
    session.pop(SESSION_KEY, None)


def cart_lines(cart: dict[int, int]) -> list[tuple[Product, int]]:
    """表示用の (商品, 数量)。非公開になった商品・消えた商品は外す"""
    lines = []
    for product_id, quantity in cart.items():
        product = db.session.get(Product, product_id)
        if product is not None and product.is_published:
            lines.append((product, quantity))
    return lines
