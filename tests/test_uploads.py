import io
from pathlib import Path

import pytest

from marche.extensions import db
from marche.models import Product
from marche.uploads import delete_image, detect_media_type, save_image

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 20


def upload_folder(app):
    return Path(app.config["UPLOAD_FOLDER"])


def files(app):
    folder = upload_folder(app)
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def post_form(client, path, image=None, **kwargs):
    data = {"name": "ほうれん草", "price": "200", "stock": "10", "description": ""}
    data.update(kwargs)
    if image is not None:
        data["image"] = image
    return client.post(path, data=data, content_type="multipart/form-data")


def make_product(producer, **kwargs):
    values = {
        "producer_id": producer.id,
        "name": "ほうれん草",
        "price": 200,
        "stock": 10,
    }
    values.update(kwargs)
    product = Product(**values)
    db.session.add(product)
    db.session.commit()
    return product


# --- detect_media_type ---


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (WEBP, "image/webp"),
        (b"", None),
        (b"hello world", None),
        (b"GIF89a" + b"\x00" * 20, None),
        (b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 20, None),  # WebP ではない RIFF
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", None),
    ],
)
def test_先頭のバイトで画像の種類を判定する(data, expected):
    assert detect_media_type(data) == expected


# --- save_image / delete_image ---


def test_UUIDのファイル名で保存される(app):
    name = save_image(JPEG, "image/jpeg")
    assert name.endswith(".jpg")
    assert len(name) == 32 + len(".jpg")
    assert (upload_folder(app) / name).read_bytes() == JPEG
    assert save_image(PNG, "image/png").endswith(".png")
    assert save_image(WEBP, "image/webp").endswith(".webp")


def test_delete_imageは写真を消し_無くてもエラーにならない(app):
    name = save_image(JPEG, "image/jpeg")
    delete_image(name)
    assert files(app) == []
    delete_image(name)
    delete_image(None)
    delete_image("")


def test_delete_imageは保存先の外を消さない(app, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("残す")
    delete_image("../outside.txt")
    assert outside.exists()


# --- 登録 ---


def test_写真つきで商品を登録できる(client, login, producer, app):
    login(producer)
    response = post_form(
        client, "/producer/products/new", (io.BytesIO(JPEG), "元の名前.jpg")
    )
    assert response.status_code == 302
    product = db.session.scalar(db.select(Product))
    assert product.image_filename.endswith(".jpg")
    assert "元の名前" not in product.image_filename  # 元のファイル名は使わない
    assert files(app) == [product.image_filename]


@pytest.mark.parametrize(
    ("data", "filename"),
    [(JPEG, "a.jpeg"), (PNG, "a.png"), (WEBP, "a.webp"), (JPEG, "A.JPG")],
)
def test_JPEG_PNG_WebPを登録できる(client, login, producer, data, filename):
    login(producer)
    response = post_form(client, "/producer/products/new", (io.BytesIO(data), filename))
    assert response.status_code == 302


def test_写真なしでも登録できる(client, login, producer, app):
    login(producer)
    response = post_form(client, "/producer/products/new")
    assert response.status_code == 302
    assert db.session.scalar(db.select(Product)).image_filename is None
    assert files(app) == []


def test_拡張子が画像でないと422(client, login, producer, app):
    login(producer)
    response = post_form(client, "/producer/products/new", (io.BytesIO(JPEG), "a.gif"))
    assert response.status_code == 422
    assert db.session.scalar(db.select(Product)) is None
    assert files(app) == []


def test_中身が画像でないと422(client, login, producer, app):
    login(producer)
    response = post_form(
        client, "/producer/products/new", (io.BytesIO(b"<?php echo 1;"), "evil.png")
    )
    assert response.status_code == 422
    assert "画像を選んでください" in response.text
    assert db.session.scalar(db.select(Product)) is None
    assert files(app) == []


def test_5MBを超えると422(client, login, producer, app):
    login(producer)
    big = JPEG + b"\x00" * (5 * 1024 * 1024)
    response = post_form(client, "/producer/products/new", (io.BytesIO(big), "a.jpg"))
    assert response.status_code == 422
    assert "5MB" in response.text
    assert files(app) == []


def test_5MBちょうどは登録できる(client, login, producer):
    login(producer)
    data = JPEG + b"\x00" * (5 * 1024 * 1024 - len(JPEG))
    response = post_form(client, "/producer/products/new", (io.BytesIO(data), "a.jpg"))
    assert response.status_code == 302


def test_リクエストが6MBを超えると413(client, login, producer, app):
    login(producer)
    huge = JPEG + b"\x00" * (7 * 1024 * 1024)
    response = post_form(client, "/producer/products/new", (io.BytesIO(huge), "a.jpg"))
    assert response.status_code == 413
    assert "大きすぎます" in response.text
    assert files(app) == []


def test_入力エラーのときは写真を保存しない(client, login, producer, app):
    login(producer)
    response = post_form(
        client, "/producer/products/new", (io.BytesIO(JPEG), "a.jpg"), price="49"
    )
    assert response.status_code == 422
    assert files(app) == []


# --- 編集 ---


def test_編集で写真を差し替えると古い写真が消える(client, login, producer, app):
    old = save_image(JPEG, "image/jpeg")
    product = make_product(producer, image_filename=old)
    login(producer)
    response = post_form(
        client, f"/producer/products/{product.id}/edit", (io.BytesIO(PNG), "b.png")
    )
    assert response.status_code == 302
    db.session.refresh(product)
    assert product.image_filename != old
    assert product.image_filename.endswith(".png")
    assert files(app) == [product.image_filename]


def test_編集で写真を選ばなければ今の写真が残る(client, login, producer, app):
    old = save_image(JPEG, "image/jpeg")
    product = make_product(producer, image_filename=old)
    login(producer)
    response = post_form(client, f"/producer/products/{product.id}/edit", name="小松菜")
    assert response.status_code == 302
    db.session.refresh(product)
    assert product.image_filename == old
    assert files(app) == [old]


def test_編集で画像でないものを選ぶと422で今の写真が残る(client, login, producer, app):
    old = save_image(JPEG, "image/jpeg")
    product = make_product(producer, image_filename=old)
    login(producer)
    response = post_form(
        client, f"/producer/products/{product.id}/edit", (io.BytesIO(b"text"), "a.png")
    )
    assert response.status_code == 422
    db.session.refresh(product)
    assert product.image_filename == old
    assert files(app) == [old]


def test_編集画面に今の写真が表示される(client, login, producer):
    name = save_image(JPEG, "image/jpeg")
    product = make_product(producer, image_filename=name)
    login(producer)
    response = client.get(f"/producer/products/{product.id}/edit")
    assert f"/static/uploads/{name}" in response.text
    assert "multipart/form-data" in response.text


def test_他人の商品の写真は差し替えられない(
    client, login, producer, other_producer, app
):
    old = save_image(JPEG, "image/jpeg")
    product = make_product(other_producer, image_filename=old)
    login(producer)
    response = post_form(
        client, f"/producer/products/{product.id}/edit", (io.BytesIO(PNG), "b.png")
    )
    assert response.status_code == 403
    db.session.refresh(product)
    assert product.image_filename == old
    assert files(app) == [old]


# --- 削除 ---


def test_商品を削除すると写真も消える(client, login, producer, app):
    name = save_image(JPEG, "image/jpeg")
    product = make_product(producer, image_filename=name)
    login(producer)
    response = client.post(f"/producer/products/{product.id}/delete")
    assert response.status_code == 302
    assert files(app) == []


def test_他人の商品を削除しようとしても写真は消えない(
    client, login, producer, other_producer, app
):
    name = save_image(JPEG, "image/jpeg")
    product = make_product(other_producer, image_filename=name)
    login(producer)
    assert client.post(f"/producer/products/{product.id}/delete").status_code == 403
    assert files(app) == [name]
