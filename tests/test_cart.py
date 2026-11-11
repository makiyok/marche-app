import pytest
from helpers import get_cart, make_order, make_product, set_cart

from marche.extensions import db


def add(client, product, quantity):
    return client.post(f"/cart/add/{product.id}", data={"quantity": str(quantity)})


def test_カートは空で表示される(client):
    response = client.get("/cart/")
    assert response.status_code == 200
    assert "カートは空です" in response.text


def test_ログインしなくてもカートに入れられる(client, producer):
    product = make_product(producer)
    response = add(client, product, 2)
    assert response.status_code == 302
    assert get_cart(client) == {str(product.id): 2}
    text = client.get("/cart/").text
    assert "ほうれん草 1束" in text
    assert "400円" in text  # 小計 200 × 2


def test_同じ商品を足すと数量が増える(client, producer):
    product = make_product(producer)
    add(client, product, 2)
    add(client, product, 3)
    assert get_cart(client) == {str(product.id): 5}


@pytest.mark.parametrize("quantity", ["0", "-1", "11", "abc", ""])
def test_数量が範囲外なら422で入らない(client, producer, quantity):
    product = make_product(producer, stock=50)
    response = client.post(f"/cart/add/{product.id}", data={"quantity": quantity})
    assert response.status_code == 422
    assert get_cart(client) is None


def test_いま買える数を超えると422(client, producer, customer):
    product = make_product(producer, stock=5)
    make_order(customer, [(product, 3)])  # 支払い待ちで3個押さえられている
    assert add(client, product, 3).status_code == 422
    assert add(client, product, 2).status_code == 302


def test_合計がいま買える数を超えると422(client, producer):
    product = make_product(producer, stock=4)
    add(client, product, 3)
    response = add(client, product, 2)
    assert response.status_code == 422
    assert "あと1個まで" in response.text
    assert get_cart(client) == {str(product.id): 3}


def test_数量は10個まで(client, producer):
    product = make_product(producer, stock=50)
    assert add(client, product, 10).status_code == 302
    assert add(client, product, 1).status_code == 422


def test_売り切れの商品は入れられない(client, producer):
    product = make_product(producer, stock=0)
    assert add(client, product, 1).status_code == 422


def test_非公開と存在しない商品は404(client, producer):
    hidden = make_product(producer, is_published=False)
    assert add(client, hidden, 1).status_code == 404
    assert client.post("/cart/add/999", data={"quantity": "1"}).status_code == 404
    assert get_cart(client) is None


def test_数量を変えられる(client, producer):
    product = make_product(producer)
    add(client, product, 2)
    response = client.post(f"/cart/update/{product.id}", data={"quantity": "5"})
    assert response.status_code == 302
    assert get_cart(client) == {str(product.id): 5}


def test_数量を0にするとカートから外れる(client, producer):
    product = make_product(producer)
    add(client, product, 2)
    client.post(f"/cart/update/{product.id}", data={"quantity": "0"})
    assert get_cart(client) == {}


@pytest.mark.parametrize("quantity", ["11", "-1", "abc", ""])
def test_数量の変更が範囲外なら422で変わらない(client, producer, quantity):
    product = make_product(producer, stock=50)
    add(client, product, 2)
    response = client.post(f"/cart/update/{product.id}", data={"quantity": quantity})
    assert response.status_code == 422
    assert get_cart(client) == {str(product.id): 2}


def test_数量の変更もいま買える数を超えられない(client, producer):
    product = make_product(producer, stock=3)
    add(client, product, 1)
    response = client.post(f"/cart/update/{product.id}", data={"quantity": "4"})
    assert response.status_code == 422
    assert get_cart(client) == {str(product.id): 1}


def test_カートにない商品の数量は変えられない(client, producer):
    product = make_product(producer)
    assert (
        client.post(f"/cart/update/{product.id}", data={"quantity": "2"}).status_code
        == 404
    )


def test_非公開になった商品はカートから外れる(client, producer):
    product = make_product(producer)
    add(client, product, 2)
    product.is_published = False
    db.session.commit()
    assert "カートは空です" in client.get("/cart/").text
    assert get_cart(client) == {}


def test_壊れたカートの値は捨てる(client, producer):
    product = make_product(producer)
    set_cart(client, {product.id: 2, "abc": 1})
    with client.session_transaction() as session:
        session["cart"]["xyz"] = "many"
    response = client.get("/cart/")
    assert response.status_code == 200
    assert "ほうれん草 1束" in response.text


def test_未ログインのカートにはログインへのリンクが出る(client, producer):
    product = make_product(producer)
    add(client, product, 1)
    text = client.get("/cart/").text
    assert "ログインして注文する" in text
    assert "注文して支払いへ進む" not in text


def test_商品名のHTMLはエスケープされる(client, producer):
    product = make_product(producer, name="<script>alert(1)</script>")
    add(client, product, 1)
    text = client.get("/cart/").text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text
