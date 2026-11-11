"""中断ページ（/orders/<id>/cancel）と、支払い完了の仮ページのテスト（T21）"""

import pytest
from helpers import make_order, make_product

from marche.extensions import db
from marche.models import OrderStatus
from marche.services.inventory import available_stock
from marche.services.payment import PaymentError


@pytest.fixture
def order(customer, producer):
    product = make_product(producer, stock=5)
    order = make_order(customer, [(product, 2)])
    order.stripe_checkout_session_id = f"cs_test_fake_{order.id}"
    db.session.commit()
    return order


def cancel(client, order):
    return client.post(f"/orders/{order.id}/cancel")


# --- 中断ページの表示 ---


def test_中断ページを本人が見られる(client, login, customer, order):
    login(customer)
    response = client.get(f"/orders/{order.id}/cancel")
    assert response.status_code == 200
    assert "お支払いを中断しました" in response.text
    assert "この注文を取り消す" in response.text


def test_管理者も中断ページを見られる(client, login, admin, order):
    login(admin)
    assert client.get(f"/orders/{order.id}/cancel").status_code == 200


def test_他人の中断ページは403(client, login, producer, order):
    login(producer)
    assert client.get(f"/orders/{order.id}/cancel").status_code == 403


def test_未ログインは中断ページからログインへ送られる(client, order):
    response = client.get(f"/orders/{order.id}/cancel")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_存在しない注文は404(client, login, customer):
    login(customer)
    assert client.get("/orders/999/cancel").status_code == 404


def test_支払い済みの注文には取り消しボタンが出ない(client, login, customer, order):
    order.status = OrderStatus.PAID
    db.session.commit()
    login(customer)
    text = client.get(f"/orders/{order.id}/cancel").text
    assert "この注文を取り消す" not in text
    assert "取り消せません" in text


# --- 取り消す（T21）---


def test_取り消すとcancelledになりSessionを期限切れにする(
    client, login, customer, order, fake_payment
):
    login(customer)
    response = cancel(client, order)
    assert response.status_code == 302
    assert response.headers["Location"] == f"/orders/{order.id}"
    db.session.refresh(order)
    assert order.status == OrderStatus.CANCELLED
    assert fake_payment.expired == [f"cs_test_fake_{order.id}"]


def test_取り消すと押さえていた在庫が戻る(client, login, customer, order):
    product = order.items[0].product
    assert available_stock(product) == 3  # 5 - 押さえ 2
    login(customer)
    cancel(client, order)
    assert available_stock(product) == 5


def test_取り消した結果が注文詳細に出る(client, login, customer, order):
    login(customer)
    cancel(client, order)
    text = client.get(f"/orders/{order.id}").text
    assert "取り消し" in text


def test_Sessionを期限切れにできなければ取り消さず注文詳細へ(
    client, login, customer, order, fake_payment
):
    fake_payment.error = PaymentError("決済ページを閉じられませんでした")
    login(customer)
    response = cancel(client, order)
    assert response.status_code == 302
    assert response.headers["Location"] == f"/orders/{order.id}"
    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING
    assert "取り消していません" in client.get(f"/orders/{order.id}").text


def test_Sessionがない注文はそのまま取り消せる(
    client, login, customer, order, fake_payment
):
    order.stripe_checkout_session_id = None
    db.session.commit()
    login(customer)
    cancel(client, order)
    db.session.refresh(order)
    assert order.status == OrderStatus.CANCELLED
    assert fake_payment.expired == []


@pytest.mark.parametrize("status", [OrderStatus.PAID, OrderStatus.CANCELLED])
def test_支払い済みや取り消し済みの注文は取り消せない(
    client, login, customer, order, fake_payment, status
):
    order.status = status
    db.session.commit()
    login(customer)
    cancel(client, order)
    db.session.refresh(order)
    assert order.status == status
    assert fake_payment.expired == []  # Stripe には何もしない


def test_他人の注文は取り消せない(client, login, producer, order, fake_payment):
    login(producer)
    assert cancel(client, order).status_code == 403
    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING
    assert fake_payment.expired == []


def test_管理者は他人の注文を取り消せる(client, login, admin, order):
    login(admin)
    cancel(client, order)
    db.session.refresh(order)
    assert order.status == OrderStatus.CANCELLED


def test_未ログインは取り消せない(client, order):
    response = cancel(client, order)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING


def test_取り消しはGETではできない(client, login, customer, order):
    login(customer)
    client.get(f"/orders/{order.id}/cancel")
    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING


# --- 支払い完了の仮ページ ---


def test_完了ページは確認中と出す(client, login, customer, order):
    login(customer)
    response = client.get(f"/orders/{order.id}/complete?session_id=cs_test_x")
    assert response.status_code == 200
    assert "お支払いを確認しています" in response.text


def test_他人の完了ページは403(client, login, producer, order):
    login(producer)
    assert client.get(f"/orders/{order.id}/complete").status_code == 403


def test_未ログインは完了ページからログインへ送られる(client, order):
    response = client.get(f"/orders/{order.id}/complete")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
