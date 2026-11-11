from datetime import timedelta

from marche.extensions import db
from marche.models import Order, OrderItem, OrderStatus, Product, now_jst

# 支払い待ちの注文が在庫を押さえておく時間（分）。
# Stripe の Checkout Session の有効期限（31分）より少し長くしている
RESERVE_MINUTES = 35


def reserved_quantity(product: Product) -> int:
    """支払い待ちで、作成から35分以内の注文が押さえている、その商品の数量の合計"""
    since = now_jst() - timedelta(minutes=RESERVE_MINUTES)
    total = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(OrderItem.quantity), 0))
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            OrderItem.product_id == product.id,
            Order.status == OrderStatus.PENDING,
            Order.created_at >= since,
        )
    )
    return int(total)


def available_stock(product: Product) -> int:
    """いま買える数 = 在庫 − 支払い待ち（35分以内）の数量の合計。0 未満にはしない"""
    return max(product.stock - reserved_quantity(product), 0)
