import json
import hashlib
import pytest
from sqlalchemy.exc import OperationalError
from app import create_app
from app.extensions import db
from app.common.auth import hash_password, ROLE_KASIR, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.auth.models import User
from app.catalog.models import Category, Menu, MenuVariant, SalesChannel
from app.inventory.models import Unit, Ingredient, Recipe, RecipeItem, StockBalance
from app.orders.models import Table, Order, STATUS_APPROVED, STATUS_PENDING_APPROVAL
from app.public.routes import PaymentGatewayError


@pytest.fixture
def client():
    app = create_app("testing")
    with app.test_client() as client:
        with app.app_context():
            db.create_all()

            # Seed test admin & kasir
            admin = User(
                username="admin",
                password_hash=hash_password("admin123"),
                pin_hash=hash_password("123456"),
                name="Admin Test",
                role=ROLE_ADMIN,
                is_active=True
            )
            kasir = User(
                username="kasir",
                password_hash=hash_password("kasir123"),
                pin_hash=hash_password("654321"),
                name="Kasir Test",
                role=ROLE_KASIR,
                is_active=True
            )
            db.session.add_all([admin, kasir])

            # Seed category & menu
            cat = Category(name="Coffee", sort_order=1)
            db.session.add(cat)
            db.session.flush()

            menu = Menu(
                category_id=cat.id,
                name="Espresso",
                base_price=10000.0,
                is_active=True,
                is_available=True
            )
            db.session.add(menu)
            db.session.flush()

            # Table
            table = Table(
                table_number="1",
                name="Meja 1",
                qr_token="test-token-meja-1",
                is_active=True
            )
            db.session.add(table)
            db.session.commit()

        yield client

        with app.app_context():
            db.drop_all()


def test_health_check(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["data"] == {"api": "connected", "database": "connected"}


def test_health_check_reports_database_unavailable(client, monkeypatch):
    def fail_health_query(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("database unavailable"))

    monkeypatch.setattr(db.session, "execute", fail_health_query)
    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.get_json()["data"]["database"] == "unavailable"


def test_production_configuration_rejects_missing_secrets(monkeypatch):
    for key in (
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY",
        "JWT_SECRET_KEY",
        "QR_HMAC_SECRET",
        "PAYMENT_GATEWAY_SERVER_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="Konfigurasi production wajib diisi"):
        create_app("production")


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password,
        "device_id": f"TEST_{username.upper()}"
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_expense_categories_are_role_protected_and_usable(client):
    admin_headers = _login(client, "admin", "admin123")
    cashier_headers = _login(client, "kasir", "kasir123")

    created = client.post(
        "/api/v1/expense-categories",
        headers=admin_headers,
        json={"name": "Kebersihan"}
    )
    assert created.status_code == 201
    category_id = created.get_json()["data"]["id"]

    cashier_categories = client.get(
        "/api/v1/expense-categories",
        headers=cashier_headers
    )
    assert cashier_categories.status_code == 200
    assert any(item["id"] == category_id for item in cashier_categories.get_json()["data"])

    expense = client.post(
        "/api/v1/expenses",
        headers=cashier_headers,
        json={"category_id": category_id, "amount": 12500}
    )
    assert expense.status_code == 201

    duplicate = client.post(
        "/api/v1/expense-categories",
        headers=admin_headers,
        json={"name": "kebersihan"}
    )
    assert duplicate.status_code == 409

    delete_in_use = client.delete(
        f"/api/v1/expense-categories/{category_id}",
        headers=admin_headers
    )
    assert delete_in_use.status_code == 409


def test_units_can_be_managed_and_referenced_by_ingredients(client):
    admin_headers = _login(client, "admin", "admin123")
    cashier_headers = _login(client, "kasir", "kasir123")

    forbidden = client.get("/api/v1/units", headers=cashier_headers)
    assert forbidden.status_code == 403

    created = client.post(
        "/api/v1/units",
        headers=admin_headers,
        json={"name": "Gram", "symbol": "g"}
    )
    assert created.status_code == 201
    unit_id = created.get_json()["data"]["id"]

    ingredient = client.post(
        "/api/v1/ingredients",
        headers=admin_headers,
        json={
            "name": "Biji Kopi",
            "unit_id": unit_id,
            "min_stock": 100,
            "last_purchase_price": 250
        }
    )
    assert ingredient.status_code == 201

    in_use = client.delete(f"/api/v1/units/{unit_id}", headers=admin_headers)
    assert in_use.status_code == 409

    invalid_unit = client.post(
        "/api/v1/ingredients",
        headers=admin_headers,
        json={"name": "Susu", "unit_id": "missing"}
    )
    assert invalid_unit.status_code == 404


def test_auth_login_and_verify_pin(client):
    # Login kasir
    res = client.post("/api/v1/auth/login", json={
        "username": "kasir",
        "password": "kasir123",
        "device_id": "TEST_DEV_01"
    })
    assert res.status_code == 200
    token = res.get_json()["data"]["access_token"]
    assert token is not None

    # Verify Kasir PIN
    res_pin = client.post(
        "/api/v1/auth/verify-pin",
        headers={"Authorization": f"Bearer {token}"},
        json={"pin": "654321"}
    )
    assert res_pin.status_code == 200
    assert res_pin.get_json()["data"]["verified"] is True


def test_get_pos_catalog(client):
    # Login first
    res_login = client.post("/api/v1/auth/login", json={
        "username": "kasir",
        "password": "kasir123",
        "device_id": "TEST_DEV_01"
    })
    token = res_login.get_json()["data"]["access_token"]

    res = client.get("/api/v1/menus/catalog", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert "categories" in data
    assert len(data["categories"]) > 0
    assert data["categories"][0]["name"] == "Coffee"


def test_pos_order_retry_with_same_idempotency_key_does_not_duplicate(client):
    headers = _login(client, "kasir", "kasir123")
    menu_id = client.get(
        "/api/v1/public/qr/test-token-meja-1/menu"
    ).get_json()["data"]["categories"][0]["menus"][0]["id"]
    payload = {
        "idempotency_key": "offline-order-retry-001",
        "order_type": "TAKE_AWAY",
        "is_paid": True,
        "items": [{
            "menu_id": menu_id,
            "item_name": "Espresso",
            "quantity": 1,
            "unit_price": 10000,
        }],
        "payment": {"payment_method": "TUNAI", "amount": 10000},
    }

    first = client.post("/api/v1/orders", headers=headers, json=payload)
    retry = client.post("/api/v1/orders", headers=headers, json=payload)

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.get_json()["data"]["id"] == first.get_json()["data"]["id"]


def test_qr_menu_and_order_creation(client):
    # 1. Access QR menu publicly without token
    res_menu = client.get("/api/v1/public/qr/test-token-meja-1/menu")
    assert res_menu.status_code == 200
    menu_data = res_menu.get_json()["data"]
    menu_id = menu_data["categories"][0]["menus"][0]["id"]

    # 2. Customer orders cash
    res_order = client.post("/api/v1/public/qr/test-token-meja-1/orders", json={
        "customer_name": "Budi",
        "order_type": "DINE_IN",
        "payment_method": "TUNAI",
        "items": [{
            "menu_id": menu_id,
            "quantity": 2
        }]
    })
    assert res_order.status_code == 201
    order_id = res_order.get_json()["data"]["order_id"]
    assert res_order.get_json()["data"]["status"] == STATUS_PENDING_APPROVAL

    # 3. Cashier logs in and checks pending orders
    res_login = client.post("/api/v1/auth/login", json={
        "username": "kasir",
        "password": "kasir123",
        "device_id": "K01"
    })
    token = res_login.get_json()["data"]["access_token"]

    res_pending = client.get("/api/v1/orders/pending-approval", headers={"Authorization": f"Bearer {token}"})
    assert res_pending.status_code == 200
    pending_list = res_pending.get_json()["data"]
    assert any(o["id"] == order_id for o in pending_list)

    # 4. Cashier approves order
    res_approve = client.post(f"/api/v1/orders/{order_id}/approve", headers={"Authorization": f"Bearer {token}"})
    assert res_approve.status_code == 200
    assert res_approve.get_json()["data"]["status"] == STATUS_APPROVED


def test_qris_payment_does_not_return_demo_qr_when_gateway_is_unconfigured(client):
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    menu_id = menu["categories"][0]["menus"][0]["id"]
    order_response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "QRIS",
            "items": [{"menu_id": menu_id, "quantity": 1}]
        }
    )
    assert order_response.status_code == 201

    order_id = order_response.get_json()["data"]["order_id"]
    payment_response = client.post(f"/api/v1/public/orders/{order_id}/pay")
    assert payment_response.status_code == 503
    assert payment_response.get_json()["success"] is False


def test_qris_charge_uses_gateway_and_returns_its_qr_payload(client, monkeypatch):
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    menu_id = menu["categories"][0]["menus"][0]["id"]
    order_response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "QRIS",
            "items": [{"menu_id": menu_id, "quantity": 1}]
        }
    )
    order_id = order_response.get_json()["data"]["order_id"]
    client.application.config["PAYMENT_GATEWAY_SERVER_KEY"] = "test-server-key"

    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            raise PaymentGatewayError("Belum ada tagihan", status_code=404)
        return {
            "qr_string": "MIDTRANS-QR-PAYLOAD",
            "expiry_time": "2026-11-11 15:00:00"
        }

    monkeypatch.setattr("app.public.routes._midtrans_request", fake_request)
    response = client.post(f"/api/v1/public/orders/{order_id}/pay")

    assert response.status_code == 200
    assert response.get_json()["data"]["qris_content"] == "MIDTRANS-QR-PAYLOAD"
    assert len(calls) == 2
    assert calls[1][2]["transaction_details"]["gross_amount"] == 10000.0


def test_qris_webhook_validates_gateway_signature_amount_and_status(client, monkeypatch):
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    menu_id = menu["categories"][0]["menus"][0]["id"]
    order_response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "QRIS",
            "items": [{"menu_id": menu_id, "quantity": 1}]
        }
    )
    order_id = order_response.get_json()["data"]["order_id"]
    order_no = order_response.get_json()["data"]["order_no"]
    server_key = "test-server-key"
    client.application.config["PAYMENT_GATEWAY_SERVER_KEY"] = server_key

    def fake_request(method, path, payload=None):
        assert method == "GET"
        assert path.endswith("/status")
        return {
            "order_id": order_no,
            "gross_amount": "10000.00",
            "transaction_status": "settlement",
            "transaction_id": "midtrans-transaction-1"
        }

    monkeypatch.setattr("app.public.routes._midtrans_request", fake_request)
    callback = {
        "order_id": order_no,
        "status_code": "200",
        "gross_amount": "10000.00",
        "transaction_status": "settlement",
        "transaction_id": "midtrans-transaction-1"
    }
    callback["signature_key"] = hashlib.sha512(
        f"{order_no}20010000.00{server_key}".encode()
    ).hexdigest()

    response = client.post("/api/v1/public/payments/webhook", json=callback)
    assert response.status_code == 200
    duplicate = client.post("/api/v1/public/payments/webhook", json=callback)
    assert duplicate.status_code == 200

    with client.application.app_context():
        order = db.session.get(Order, order_id)
        assert order.payment_status == "PAID"
        assert order.status == "APPROVED"
        assert len(order.payments) == 1


def test_qr_order_rejects_invalid_quantities(client):
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    menu_id = menu["categories"][0]["menus"][0]["id"]

    response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "TUNAI",
            "items": [{"menu_id": menu_id, "quantity": -1}]
        }
    )
    assert response.status_code == 400
