from marche.extensions import db
from marche.models import Order, OrderItem, OrderStatus, Product, now_jst


def make_product(producer, **kwargs):
    values = {
        "producer_id": producer.id,
        "name": "ほうれん草 1束",
        "description": "朝採りです",
        "price": 200,
        "stock": 10,
        "is_published": True,
    }
    values.update(kwargs)
    product = Product(**values)
    db.session.add(product)
    db.session.commit()
    return product


def make_order(user, lines, status=OrderStatus.PENDING, created_at=None):
    """lines は (商品, 数量) のリスト。単価と商品名は、いまの商品から写す"""
    items = [
        OrderItem(
            product_id=product.id,
            product_name=product.name,
            unit_price=product.price,
            quantity=quantity,
            subtotal=product.price * quantity,
        )
        for product, quantity in lines
    ]
    order = Order(
        user_id=user.id,
        status=status,
        total_amount=sum(item.subtotal for item in items),
        items=items,
        created_at=created_at or now_jst(),
    )
    db.session.add(order)
    db.session.commit()
    return order


def set_cart(client, cart):
    """セッションのカートを直接入れる（{商品ID: 数量}）"""
    with client.session_transaction() as session:
        session["cart"] = {str(k): v for k, v in cart.items()}


def get_cart(client):
    with client.session_transaction() as session:
        return session.get("cart")
