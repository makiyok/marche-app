from marche.extensions import db
from marche.models import Order, OrderItem, OrderStatus, Product, User
from marche.services.inventory import available_stock

MAX_QUANTITY = 10


class OrderError(Exception):
    """注文を作れないとき。メッセージは、そのまま画面に出せる日本語"""


def create_order(user: User, cart: dict[int, int]) -> Order:
    """カート（{商品ID: 数量}）から、支払い待ちの注文を作る。

    商品名・単価・金額は、すべてデータベースから取る（カートやフォームの値は使わない）。
    在庫はここでは減らさない（支払いが確定したときに減らす）。
    """
    if not cart:
        raise OrderError("カートが空です")

    items = []
    for product_id, quantity in cart.items():
        product = db.session.get(Product, product_id)
        if product is None or not product.is_published:
            raise OrderError("買えなくなった商品があります。カートを確かめてください")
        if not 1 <= quantity <= MAX_QUANTITY:
            raise OrderError(f"{product.name}の数量は 1〜{MAX_QUANTITY} にしてください")
        if quantity > available_stock(product):
            raise OrderError(f"{product.name}は在庫が足りません")
        items.append(
            OrderItem(
                product_id=product.id,
                product_name=product.name,
                unit_price=product.price,
                quantity=quantity,
                subtotal=product.price * quantity,
            )
        )

    order = Order(
        user_id=user.id,
        status=OrderStatus.PENDING,
        total_amount=sum(item.subtotal for item in items),
        items=items,
    )
    db.session.add(order)
    db.session.commit()
    return order
