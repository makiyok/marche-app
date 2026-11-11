import pytest
from helpers import get_cart, make_order, make_product, set_cart

from marche.extensions import db
from marche.models import Order, OrderItem, OrderStatus
from marche.services.orders import OrderError, create_order


def place_order(client):
    return client.post("/orders/")


def orders():
    return db.session.scalars(db.select(Order)).all()


# --- 注文を作る（T9）---


def test_注文すると支払い待ちの注文ができて注文詳細へ移る(
    client, login, customer, producer
):
    product = make_product(producer, price=300)
    login(customer)
    set_cart(client, {product.id: 2})
    response = place_order(client)
    order = db.session.scalar(db.select(Order))
    assert response.status_code == 303
    assert response.headers["Location"] == f"/orders/{order.id}"
    assert order.user_id == customer.id
    assert order.status == OrderStatus.PENDING
    assert order.total_amount == 600
    assert order.stripe_checkout_session_id is None


def test_注文の明細は注文時点の商品名と単価を持つ(client, login, customer, producer):
    product = make_product(producer, name="ほうれん草 1束", price=300)
    login(customer)
    set_cart(client, {product.id: 3})
    place_order(client)
    item = db.session.scalar(db.select(OrderItem))
    assert (item.product_name, item.unit_price, item.quantity, item.subtotal) == (
        "ほうれん草 1束",
        300,
        3,
        900,
    )


def test_注文後に商品の価格や名前を変えても注文は変わらない(
    client, login, customer, producer
):
    product = make_product(producer, name="ほうれん草 1束", price=300)
    login(customer)
    set_cart(client, {product.id: 2})
    place_order(client)
    product.name = "名前を変えた"
    product.price = 999
    db.session.commit()
    order = db.session.scalar(db.select(Order))
    assert order.total_amount == 600
    assert order.items[0].product_name == "ほうれん草 1束"
    assert order.items[0].unit_price == 300
    text = client.get(f"/orders/{order.id}").text
    assert "ほうれん草 1束" in text
    assert "600円" in text


def test_金額はデータベースの価格で計算しフォームの金額は無視する(
    client, login, customer, producer
):
    product = make_product(producer, price=300)
    login(customer)
    set_cart(client, {product.id: 2})
    client.post("/orders/", data={"total_amount": "1", "price": "1", "unit_price": "1"})
    assert db.session.scalar(db.select(Order)).total_amount == 600


def test_複数の商品をまとめて注文できる(
    client, login, customer, producer, other_producer
):
    a = make_product(producer, name="ほうれん草", price=200)
    b = make_product(other_producer, name="トマト", price=600)
    login(customer)
    set_cart(client, {a.id: 2, b.id: 1})
    place_order(client)
    order = db.session.scalar(db.select(Order))
    assert len(order.items) == 2
    assert order.total_amount == 1000


def test_注文するとカートが空になる(client, login, customer, producer):
    product = make_product(producer)
    login(customer)
    set_cart(client, {product.id: 1})
    place_order(client)
    assert get_cart(client) is None


def test_注文しただけでは在庫は減らない(client, login, customer, producer):
    product = make_product(producer, stock=10)
    login(customer)
    set_cart(client, {product.id: 3})
    place_order(client)
    db.session.refresh(product)
    assert product.stock == 10  # 減るのは支払いが確定したとき


def test_生産者も購入者として注文できる(client, login, producer, other_producer):
    product = make_product(other_producer)
    login(producer)
    set_cart(client, {product.id: 1})
    assert place_order(client).status_code == 303


# --- 注文できないとき（T10）---


def test_未ログインはログインへ送られ注文は作られない(client, producer):
    product = make_product(producer)
    set_cart(client, {product.id: 1})
    response = place_order(client)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert "next=/cart/" in response.headers["Location"]
    assert orders() == []


def test_カートが空なら注文できない(client, login, customer):
    login(customer)
    response = place_order(client)
    assert response.status_code == 422
    assert "カートが空です" in response.text
    assert orders() == []


def test_在庫を超える数は注文できない(client, login, customer, producer):
    product = make_product(producer, stock=2)
    login(customer)
    set_cart(client, {product.id: 3})
    response = place_order(client)
    assert response.status_code == 422
    assert "在庫が足りません" in response.text
    assert orders() == []


def test_他の人の支払い待ちで押さえられた分は注文できない(
    client, login, customer, producer, other_producer
):
    product = make_product(producer, stock=3)
    make_order(other_producer, [(product, 2)])
    login(customer)
    set_cart(client, {product.id: 2})
    assert place_order(client).status_code == 422
    assert len(orders()) == 1  # 最初の注文だけ


def test_非公開の商品は注文できない(client, login, customer, producer):
    product = make_product(producer, is_published=False)
    login(customer)
    set_cart(client, {product.id: 1})
    assert place_order(client).status_code == 422
    assert orders() == []


def test_一部でも買えない商品があれば注文全体が作られない(
    client, login, customer, producer
):
    ok = make_product(producer, name="ほうれん草")
    ng = make_product(producer, name="トマト", stock=1)
    login(customer)
    set_cart(client, {ok.id: 1, ng.id: 5})
    assert place_order(client).status_code == 422
    assert orders() == []


@pytest.mark.parametrize("quantity", [0, 11, -1])
def test_数量が範囲外なら注文できない(client, login, customer, producer, quantity):
    product = make_product(producer, stock=50)
    login(customer)
    set_cart(client, {product.id: quantity})
    place_order(client)
    assert orders() == []


def test_注文できなかったときカートは残る(client, login, customer, producer):
    product = make_product(producer, stock=1)
    login(customer)
    set_cart(client, {product.id: 5})
    place_order(client)
    assert get_cart(client) == {str(product.id): 5}


def test_create_orderはOrderErrorを投げる(customer, producer):
    product = make_product(producer, stock=1)
    with pytest.raises(OrderError):
        create_order(customer, {product.id: 2})
    with pytest.raises(OrderError):
        create_order(customer, {})
    with pytest.raises(OrderError):
        create_order(customer, {999: 1})
    assert orders() == []


# --- 注文詳細（T12）---


def test_本人は注文詳細を見られる(client, login, customer, producer):
    product = make_product(producer, name="ほうれん草 1束", price=300)
    order = make_order(customer, [(product, 2)])
    login(customer)
    response = client.get(f"/orders/{order.id}")
    assert response.status_code == 200
    assert "ほうれん草 1束" in response.text
    assert "600円" in response.text
    assert "支払い待ち" in response.text
    assert "月" in response.text  # 「11月14日(土) 10:00」の形式の日付


def test_他人の注文詳細は403(client, login, customer, producer, other_producer):
    product = make_product(producer)
    order = make_order(other_producer, [(product, 1)])
    login(customer)
    assert client.get(f"/orders/{order.id}").status_code == 403


def test_管理者は他人の注文詳細を見られる(client, login, customer, producer, admin):
    product = make_product(producer)
    order = make_order(customer, [(product, 1)])
    login(admin)
    assert client.get(f"/orders/{order.id}").status_code == 200


def test_未ログインは注文詳細からログインへ送られる(client, customer, producer):
    product = make_product(producer)
    order = make_order(customer, [(product, 1)])
    response = client.get(f"/orders/{order.id}")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_存在しない注文は404(client, login, customer):
    login(customer)
    assert client.get("/orders/999").status_code == 404


@pytest.mark.parametrize(
    ("status", "label"),
    [
        (OrderStatus.PENDING, "支払い待ち"),
        (OrderStatus.PAID, "支払い済み"),
        (OrderStatus.CANCELLED, "取り消し"),
    ],
)
def test_注文の状態が表示される(client, login, customer, producer, status, label):
    product = make_product(producer)
    order = make_order(customer, [(product, 1)], status=status)
    login(customer)
    assert label in client.get(f"/orders/{order.id}").text
