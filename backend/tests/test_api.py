import json
import pytest
from app import create_app
from app.extensions import db
from app.common.auth import hash_password, ROLE_KASIR, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.auth.models import User
from app.catalog.models import Category, Menu, MenuVariant, SalesChannel
from app.inventory.models import Unit, Ingredient, Recipe, RecipeItem, StockBalance
from app.orders.models import Table, Order, STATUS_APPROVED, STATUS_PENDING_APPROVAL


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

