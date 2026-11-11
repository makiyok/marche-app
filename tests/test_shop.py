from marche.extensions import db
from marche.models import Product


def make_product(producer, **kwargs):
    values = {
        "producer_id": producer.id,
        "name": "ほうれん草",
        "price": 1200,
        "stock": 10,
        "is_published": True,
    }
    values.update(kwargs)
    product = Product(**values)
    db.session.add(product)
    db.session.commit()
    return product


def test_公開中の商品が一覧に出る(client, producer):
    make_product(producer, name="ほうれん草")
    response = client.get("/")
    assert response.status_code == 200
    assert "ほうれん草" in response.text
    assert "1,200円" in response.text
    assert "高原ファーム" in response.text  # 生産者名


def test_非公開の商品は一覧に出ない(client, producer):
    make_product(producer, name="準備中の商品", is_published=False)
    make_product(producer, name="公開中の商品")
    text = client.get("/").text
    assert "公開中の商品" in text
    assert "準備中の商品" not in text


def test_在庫0は売り切れと表示される(client, producer):
    make_product(producer, name="売り切れの商品", stock=0)
    assert "売り切れ" in client.get("/").text


def test_在庫があれば売り切れとは出ない(client, producer):
    make_product(producer, stock=3)
    text = client.get("/").text
    assert "売り切れ" not in text
    assert "在庫 3" in text


def test_商品がないときは案内が出る(client):
    assert "いま買える商品はありません" in client.get("/").text


def test_新しい商品が先に並ぶ(client, producer):
    make_product(producer, name="古い商品")
    make_product(producer, name="新しい商品")
    text = client.get("/").text
    assert text.index("新しい商品") < text.index("古い商品")


def test_写真つきの商品は写真が出る(client, producer):
    make_product(producer, image_filename="abc.jpg")
    assert "/static/uploads/abc.jpg" in client.get("/").text


def test_ログインしていなくても見られる(client, producer):
    make_product(producer)
    assert client.get("/").status_code == 200


def test_商品名のHTMLはエスケープされる(client, producer):
    make_product(producer, name="<script>alert(1)</script>")
    text = client.get("/").text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text
