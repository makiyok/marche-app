import pytest

from marche.extensions import db
from marche.models import Product


def make_product(producer, **kwargs):
    values = {
        "producer_id": producer.id,
        "name": "ほうれん草 1束",
        "description": "朝採りです",
        "price": 200,
        "stock": 10,
        "is_published": False,
    }
    values.update(kwargs)
    product = Product(**values)
    db.session.add(product)
    db.session.commit()
    return product


def form_data(**kwargs):
    data = {
        "name": "ほうれん草 1束",
        "price": "200",
        "stock": "10",
        "description": "朝採りです",
    }
    data.update(kwargs)
    return data


# --- 一覧 ---


def test_自分の商品だけが一覧に出る(client, login, producer, other_producer):
    make_product(producer, name="自分の商品")
    make_product(other_producer, name="他人の商品")
    login(producer)
    response = client.get("/producer/products")
    assert response.status_code == 200
    assert "自分の商品" in response.text
    assert "他人の商品" not in response.text
    assert "200円" in response.text


def test_未ログインはログイン画面へ送られる(client):
    response = client.get("/producer/products")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/producer/products"),
        ("get", "/producer/products/new"),
        ("post", "/producer/products/new"),
        ("get", "/producer/products/1/edit"),
        ("post", "/producer/products/1/toggle"),
        ("post", "/producer/products/1/delete"),
    ],
)
def test_購入者は生産者の画面に入れない(client, login, customer, method, path):
    login(customer)
    assert getattr(client, method)(path).status_code == 403


# --- 登録 ---


def test_商品を登録できる(client, login, producer):
    login(producer)
    response = client.post("/producer/products/new", data=form_data())
    assert response.status_code == 302
    product = db.session.scalar(db.select(Product))
    assert product.producer_id == producer.id
    assert product.name == "ほうれん草 1束"
    assert product.price == 200
    assert product.stock == 10
    assert product.is_published is False  # チェックしなければ非公開
    assert product.image_filename is None


def test_公開するにチェックすると公開で登録される(client, login, producer):
    login(producer)
    client.post("/producer/products/new", data=form_data(is_published="y"))
    assert db.session.scalar(db.select(Product)).is_published is True


def test_在庫0と価格の下限上限で登録できる(client, login, producer):
    login(producer)
    for price in ("50", "100000"):
        response = client.post(
            "/producer/products/new", data=form_data(price=price, stock="0")
        )
        assert response.status_code == 302
    assert len(db.session.scalars(db.select(Product)).all()) == 2


def test_紹介文は空でも登録できる(client, login, producer):
    login(producer)
    response = client.post("/producer/products/new", data=form_data(description=""))
    assert response.status_code == 302
    assert db.session.scalar(db.select(Product)).description == ""


def test_producer_idはフォームから受け取らない(client, login, producer, other_producer):
    login(producer)
    client.post(
        "/producer/products/new", data=form_data(producer_id=str(other_producer.id))
    )
    assert db.session.scalar(db.select(Product)).producer_id == producer.id


@pytest.mark.parametrize(
    "bad",
    [
        {"name": ""},
        {"name": "あ" * 51},
        {"price": ""},
        {"price": "49"},
        {"price": "100001"},
        {"price": "abc"},
        {"price": "1.5"},
        {"stock": ""},
        {"stock": "-1"},
        {"stock": "1000"},
        {"stock": "abc"},
        {"description": "あ" * 2001},
    ],
)
def test_不正な入力は422で登録されない(client, login, producer, bad):
    login(producer)
    response = client.post("/producer/products/new", data=form_data(**bad))
    assert response.status_code == 422
    assert db.session.scalar(db.select(Product)) is None


def test_上限ちょうどの文字数は登録できる(client, login, producer):
    login(producer)
    response = client.post(
        "/producer/products/new",
        data=form_data(name="あ" * 50, description="あ" * 2000),
    )
    assert response.status_code == 302


def test_商品名のHTMLはエスケープして表示される(client, login, producer):
    make_product(producer, name="<script>alert(1)</script>")
    login(producer)
    text = client.get("/producer/products").text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


# --- 編集 ---


def test_商品を編集できる(client, login, producer):
    product = make_product(producer)
    login(producer)
    response = client.post(
        f"/producer/products/{product.id}/edit",
        data=form_data(name="小松菜", price="300", stock="0", is_published="y"),
    )
    assert response.status_code == 302
    db.session.refresh(product)
    assert product.name == "小松菜"
    assert product.price == 300
    assert product.stock == 0
    assert product.is_published is True


def test_編集画面に今の値が入っている(client, login, producer):
    product = make_product(producer, name="小松菜")
    login(producer)
    response = client.get(f"/producer/products/{product.id}/edit")
    assert response.status_code == 200
    assert "小松菜" in response.text


def test_編集するとupdated_atが変わる(client, login, producer):
    product = make_product(producer)
    old = product.updated_at
    login(producer)
    client.post(f"/producer/products/{product.id}/edit", data=form_data(name="小松菜"))
    db.session.refresh(product)
    assert product.updated_at > old


def test_不正な入力の編集は422で変更されない(client, login, producer):
    product = make_product(producer)
    login(producer)
    response = client.post(
        f"/producer/products/{product.id}/edit", data=form_data(price="49")
    )
    assert response.status_code == 422
    db.session.refresh(product)
    assert product.price == 200


def test_他人の商品は編集できない(client, login, producer, other_producer):
    product = make_product(other_producer)
    login(producer)
    assert client.get(f"/producer/products/{product.id}/edit").status_code == 403
    response = client.post(
        f"/producer/products/{product.id}/edit", data=form_data(name="乗っ取り")
    )
    assert response.status_code == 403
    db.session.refresh(product)
    assert product.name == "ほうれん草 1束"


def test_存在しない商品は404(client, login, producer):
    login(producer)
    assert client.get("/producer/products/999/edit").status_code == 404
    assert client.post("/producer/products/999/toggle").status_code == 404
    assert client.post("/producer/products/999/delete").status_code == 404


# --- 公開 / 非公開 ---


def test_公開と非公開を切り替えられる(client, login, producer):
    product = make_product(producer, is_published=False)
    login(producer)
    client.post(f"/producer/products/{product.id}/toggle")
    db.session.refresh(product)
    assert product.is_published is True
    client.post(f"/producer/products/{product.id}/toggle")
    db.session.refresh(product)
    assert product.is_published is False


def test_他人の商品は切り替えられない(client, login, producer, other_producer):
    product = make_product(other_producer, is_published=False)
    login(producer)
    assert client.post(f"/producer/products/{product.id}/toggle").status_code == 403
    db.session.refresh(product)
    assert product.is_published is False


def test_切り替えはGETではできない(client, login, producer):
    product = make_product(producer)
    login(producer)
    assert client.get(f"/producer/products/{product.id}/toggle").status_code == 405


# --- 削除 ---


def test_商品を削除できる(client, login, producer):
    product = make_product(producer)
    login(producer)
    response = client.post(f"/producer/products/{product.id}/delete")
    assert response.status_code == 302
    assert db.session.get(Product, product.id) is None


def test_他人の商品は削除できない(client, login, producer, other_producer):
    product = make_product(other_producer)
    login(producer)
    assert client.post(f"/producer/products/{product.id}/delete").status_code == 403
    assert db.session.get(Product, product.id) is not None


def test_削除はGETではできない(client, login, producer):
    product = make_product(producer)
    login(producer)
    assert client.get(f"/producer/products/{product.id}/delete").status_code == 405
    assert db.session.get(Product, product.id) is not None


def test_管理者も生産者の画面には入れない(client, login, admin):
    login(admin)
    assert client.get("/producer/products").status_code == 403


# --- 注文がある商品は削除できない ---


def test_注文がある商品は削除できない(client, login, producer, customer):
    from helpers import make_order

    product = make_product(producer)
    make_order(customer, [(product, 1)])
    login(producer)
    response = client.post(f"/producer/products/{product.id}/delete")
    assert response.status_code == 302
    assert db.session.get(Product, product.id) is not None
    assert "注文がある商品は削除できません" in client.get("/producer/products").text


def test_注文がある商品は非公開にはできる(client, login, producer, customer):
    from helpers import make_order

    product = make_product(producer, is_published=True)
    make_order(customer, [(product, 1)])
    login(producer)
    client.post(f"/producer/products/{product.id}/toggle")
    db.session.refresh(product)
    assert product.is_published is False
