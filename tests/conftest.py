import pytest

from marche import create_app
from marche.extensions import db
from marche.models import Role, User

# 本物の外部サービス（Stripe、拡張で足す Claude API）は、テストでは呼ばない。
# フェイク（偽物）のクラスを作り、create_app() の設定で差し替える（AI の拡張では FakeAI を足す）。


class FakePayment:
    """Stripe の代わり。services/payment.py と同じ名前の関数を持ち、呼ばれた内容を記録する。

    error に例外を入れておくと、どの関数もそれを投げる（失敗の場面を試せる）。
    """

    def __init__(self):
        self.error = None
        self.created = []  # 決済ページを作った注文の ID
        self.sessions = {}  # session_id → retrieve_session が返すもの
        self.expired = []  # 期限切れにした session_id

    def create_checkout_session(self, order):
        if self.error:
            raise self.error
        self.created.append(order.id)
        session_id = f"cs_test_fake_{order.id}"
        return session_id, f"https://checkout.stripe.test/pay/{session_id}"

    def retrieve_session(self, session_id):
        if self.error:
            raise self.error
        return self.sessions[session_id]

    def expire_session(self, session_id):
        if self.error:
            raise self.error
        self.expired.append(session_id)


@pytest.fixture
def fake_payment():
    return FakePayment()


@pytest.fixture
def app(tmp_path, fake_payment):
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            # テストの写真が marche/static/uploads に溜まらないようにする
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
            "PAYMENT_SERVICE": fake_payment,
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(role, email, name):
    user = User(name=name, email=email, role=role)
    user.set_password("password")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def customer(app):
    return _make_user(Role.CUSTOMER, "customer@example.com", "購入者")


@pytest.fixture
def producer(app):
    return _make_user(Role.PRODUCER, "producer@example.com", "高原ファーム")


@pytest.fixture
def other_producer(app):
    return _make_user(Role.PRODUCER, "other@example.com", "別の農園")


@pytest.fixture
def admin(app):
    return _make_user(Role.ADMIN, "admin@example.com", "管理者")


@pytest.fixture
def login(client):
    def do_login(user):
        return client.post("/login", data={"email": user.email, "password": "password"})

    return do_login
