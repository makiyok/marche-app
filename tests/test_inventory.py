from datetime import timedelta

from helpers import make_order, make_product

from marche.models import OrderStatus, now_jst
from marche.services.inventory import available_stock


def test_注文がなければ在庫のまま(producer):
    product = make_product(producer, stock=10)
    assert available_stock(product) == 10


def test_支払い待ちの数だけいま買える数が減る(producer, customer):
    product = make_product(producer, stock=10)
    make_order(customer, [(product, 3)])
    make_order(customer, [(product, 2)])
    assert available_stock(product) == 5


def test_35分を過ぎた支払い待ちは引かない(producer, customer):
    product = make_product(producer, stock=10)
    make_order(customer, [(product, 4)], created_at=now_jst() - timedelta(minutes=36))
    assert available_stock(product) == 10


def test_35分以内の支払い待ちは引く(producer, customer):
    product = make_product(producer, stock=10)
    make_order(customer, [(product, 4)], created_at=now_jst() - timedelta(minutes=34))
    assert available_stock(product) == 6


def test_取り消しと支払い済みは引かない(producer, customer):
    # 支払い済みは、確定のときに stock そのものを減らすので、ここでは引かない
    product = make_product(producer, stock=10)
    make_order(customer, [(product, 3)], status=OrderStatus.CANCELLED)
    make_order(customer, [(product, 2)], status=OrderStatus.PAID)
    assert available_stock(product) == 10


def test_ほかの商品の注文は引かない(producer, customer):
    product = make_product(producer, stock=10)
    other = make_product(producer, name="小松菜", stock=10)
    make_order(customer, [(other, 5)])
    assert available_stock(product) == 10


def test_0未満にはならない(producer, customer):
    product = make_product(producer, stock=2)
    make_order(customer, [(product, 5)])
    assert available_stock(product) == 0
