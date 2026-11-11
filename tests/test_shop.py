from helpers import make_order, make_product


def test_公開中の商品が一覧に出る(client, producer):
    make_product(producer, name="ほうれん草", price=1200)
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


# --- 商品詳細（S2）と「いま買える数」---


def test_商品詳細が表示される(client, producer):
    product = make_product(
        producer, name="高原トマト", description="甘いです", price=600, stock=8
    )
    response = client.get(f"/products/{product.id}")
    assert response.status_code == 200
    assert "高原トマト" in response.text
    assert "甘いです" in response.text
    assert "600円" in response.text
    assert "高原ファーム" in response.text
    assert "在庫 8" in response.text
    assert "カートに入れる" in response.text


def test_一覧から商品詳細へリンクする(client, producer):
    product = make_product(producer)
    assert f"/products/{product.id}" in client.get("/").text


def test_売り切れの詳細にはカートに入れるボタンが出ない(client, producer):
    product = make_product(producer, stock=0)
    text = client.get(f"/products/{product.id}").text
    assert "売り切れ" in text
    assert "カートに入れる" not in text


def test_数量の選択肢は10かいま買える数のどちらか小さい方まで(client, producer):
    many = make_product(producer, name="たくさん", stock=50)
    few = make_product(producer, name="少し", stock=3)
    many_text = client.get(f"/products/{many.id}").text
    few_text = client.get(f"/products/{few.id}").text
    assert '<option value="10">' in many_text
    assert '<option value="11">' not in many_text
    assert '<option value="3">' in few_text
    assert '<option value="4">' not in few_text


def test_支払い待ちの数だけ一覧と詳細の在庫が減る(client, producer, customer):
    product = make_product(producer, stock=5)
    make_order(customer, [(product, 2)])
    assert "在庫 3" in client.get("/").text
    assert "在庫 3" in client.get(f"/products/{product.id}").text


def test_全て押さえられると売り切れになる(client, producer, customer):
    product = make_product(producer, stock=2)
    make_order(customer, [(product, 2)])
    assert "売り切れ" in client.get("/").text


def test_非公開の商品の詳細は他の人には404(
    client, login, producer, other_producer, customer
):
    product = make_product(producer, is_published=False)
    assert client.get(f"/products/{product.id}").status_code == 404  # 未ログイン
    login(customer)
    assert client.get(f"/products/{product.id}").status_code == 404


def test_非公開の商品の詳細は出品者と管理者には見える(client, login, producer, admin):
    product = make_product(producer, name="準備中の商品", is_published=False)
    login(producer)
    response = client.get(f"/products/{product.id}")
    assert response.status_code == 200
    assert "非公開の商品です" in response.text
    assert "カートに入れる" not in response.text
    client.post("/logout")
    login(admin)
    assert client.get(f"/products/{product.id}").status_code == 200


def test_他の生産者には非公開の商品の詳細は見えない(
    client, login, producer, other_producer
):
    product = make_product(producer, is_published=False)
    login(other_producer)
    assert client.get(f"/products/{product.id}").status_code == 404


def test_存在しない商品は404(client):
    assert client.get("/products/999").status_code == 404
