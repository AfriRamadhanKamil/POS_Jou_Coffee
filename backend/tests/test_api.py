import json
import hashlib
import pytest
import redis
from sqlalchemy.exc import OperationalError
from app import create_app
from app.extensions import db, socketio
from app.common.auth import hash_password, ROLE_KASIR, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.auth.models import User, Device, AuditLog
from app.catalog.models import Category, Menu, MenuVariant, SalesChannel
from app.inventory.models import Unit, Ingredient, Recipe, RecipeItem, StockBalance
from app.orders.models import (
    Table, Order, Payment, STATUS_APPROVED, STATUS_PENDING_APPROVAL,
    STATUS_AWAITING_PAYMENT, STATUS_EXPIRED
)
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


def test_socketio_orders_namespace_requires_active_device_token(client):
    headers = _login(client, "kasir", "kasir123")
    token = headers["Authorization"].removeprefix("Bearer ")

    authenticated = socketio.test_client(
        client.application,
        namespace="/ws",
        auth={"token": token}
    )
    assert authenticated.is_connected("/ws")

    unauthenticated = socketio.test_client(client.application, namespace="/ws")
    assert not unauthenticated.is_connected("/ws")
    authenticated.emit("join_device", {"device_id": "OTHER_DEVICE"}, namespace="/ws")
    authenticated.disconnect(namespace="/ws")


def test_health_check(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["data"] == {
        "api": "connected",
        "database": "connected",
        "redis": "not_required"
    }


def test_security_headers_and_authentication_rate_limit(client):
    health = client.get("/api/v1/health")
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in health.headers["Content-Security-Policy"]

    client.application.config["AUTH_LOGIN_RATE_LIMIT"] = "1 per minute"
    credentials = {
        "username": "kasir",
        "password": "kasir123",
        "device_id": "LIMIT_TEST_DEVICE"
    }
    first = client.post("/api/v1/auth/login", json=credentials)
    second = client.post("/api/v1/auth/login", json=credentials)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.get_json()["success"] is False


def test_health_check_reports_configured_redis_status(client, monkeypatch):
    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            pass

    client.application.config["SOCKETIO_MESSAGE_QUEUE"] = "redis://localhost:6379/0"
    monkeypatch.setattr(redis.Redis, "from_url", lambda url: FakeRedis())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.get_json()["data"]["redis"] == "connected"


def test_health_check_reports_redis_unavailable(client, monkeypatch):
    class UnavailableRedis:
        def ping(self):
            raise redis.exceptions.ConnectionError("Redis unavailable")

        def close(self):
            pass

    client.application.config["SOCKETIO_MESSAGE_QUEUE"] = "redis://localhost:6379/0"
    monkeypatch.setattr(redis.Redis, "from_url", lambda url: UnavailableRedis())

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.get_json()["data"]["redis"] == "unavailable"


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
        json={
            "category_id": category_id,
            "amount": 12500,
            "idempotency_key": "test-expense-idempotency-001"
        }
    )
    assert expense.status_code == 201
    expense_retry = client.post(
        "/api/v1/expenses",
        headers=cashier_headers,
        json={
            "category_id": category_id,
            "amount": 12500,
            "idempotency_key": "test-expense-idempotency-001"
        }
    )
    assert expense_retry.status_code == 200
    assert expense_retry.get_json()["data"]["id"] == expense.get_json()["data"]["id"]

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


def test_shift_cash_reconciliation_and_write_retries_are_idempotent(client):
    admin_headers = _login(client, "admin", "admin123")
    cashier_headers = _login(client, "kasir", "kasir123")
    category = client.post(
        "/api/v1/expense-categories",
        headers=admin_headers,
        json={"name": "Shift Supplies"}
    ).get_json()["data"]

    opened = client.post(
        "/api/v1/shifts/open",
        headers=cashier_headers,
        json={
            "idempotency_key": "shift-open-001",
            "starting_cash": 1000
        }
    )
    assert opened.status_code == 201
    shift_id = opened.get_json()["data"]["id"]
    open_retry = client.post(
        "/api/v1/shifts/open",
        headers=cashier_headers,
        json={
            "idempotency_key": "shift-open-001",
            "starting_cash": 1000
        }
    )
    assert open_retry.status_code == 200
    assert open_retry.get_json()["data"]["id"] == shift_id

    movement_payload = {
        "idempotency_key": "shift-cash-in-001",
        "shift_id": shift_id,
        "type": "CASH_IN",
        "amount": 500
    }
    movement = client.post(
        "/api/v1/cash-movements",
        headers=cashier_headers,
        json=movement_payload
    )
    movement_retry = client.post(
        "/api/v1/cash-movements",
        headers=cashier_headers,
        json=movement_payload
    )
    assert movement.status_code == 201
    assert movement_retry.status_code == 200
    assert movement_retry.get_json()["data"]["id"] == movement.get_json()["data"]["id"]

    expense_payload = {
        "idempotency_key": "shift-expense-001",
        "category_id": category["id"],
        "amount": 1000,
        "shift_id": shift_id
    }
    expense = client.post(
        "/api/v1/expenses",
        headers=cashier_headers,
        json=expense_payload
    )
    assert expense.status_code == 201

    menu_id = client.get(
        "/api/v1/public/qr/test-token-meja-1/menu"
    ).get_json()["data"]["categories"][0]["menus"][0]["id"]
    order = client.post(
        "/api/v1/orders",
        headers=cashier_headers,
        json={
            "idempotency_key": "shift-cash-sale-001",
            "order_type": "TAKE_AWAY",
            "shift_id": shift_id,
            "items": [{
                "menu_id": menu_id,
                "item_name": "Coffee",
                "quantity": 1,
                "unit_price": 10000
            }],
            "payment": {"payment_method": "CASH", "amount": 12000}
        }
    )
    assert order.status_code == 201

    current = client.get("/api/v1/shifts/current", headers=cashier_headers)
    assert current.get_json()["data"]["expected_cash_drawer"] == 10500.0
    close_payload = {
        "idempotency_key": "shift-close-001",
        "ending_cash_actual": 10500
    }
    closed = client.post(
        f"/api/v1/shifts/{shift_id}/close",
        headers=cashier_headers,
        json=close_payload
    )
    close_retry = client.post(
        f"/api/v1/shifts/{shift_id}/close",
        headers=cashier_headers,
        json=close_payload
    )
    assert closed.status_code == 200
    assert closed.get_json()["data"]["cash_difference"] == 0.0
    assert close_retry.status_code == 200


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


def test_login_accepts_pin_and_requires_device_id(client):
    missing_device = client.post("/api/v1/auth/login", json={
        "username": "kasir",
        "pin": "654321",
    })
    assert missing_device.status_code == 400

    pin_login = client.post("/api/v1/auth/login", json={
        "username": "kasir",
        "pin": "654321",
        "device_id": "PIN_DEVICE_01",
    })
    assert pin_login.status_code == 200
    assert pin_login.get_json()["data"]["access_token"]


def test_login_enforces_active_device_limit(client):
    client.application.config["MAX_ACTIVE_DEVICES_PER_USER"] = 1
    first_device = client.post("/api/v1/auth/login", json={
        "username": "kasir",
        "password": "kasir123",
        "device_id": "LIMIT_DEVICE_01",
    })
    second_device = client.post("/api/v1/auth/login", json={
        "username": "kasir",
        "password": "kasir123",
        "device_id": "LIMIT_DEVICE_02",
    })

    assert first_device.status_code == 200
    assert second_device.status_code == 403


def test_inventory_ledger_purchase_sale_void_and_insufficient_stock(client):
    admin_headers = _login(client, "admin", "admin123")
    cashier_headers = _login(client, "kasir", "kasir123")
    unit = client.post(
        "/api/v1/units",
        headers=admin_headers,
        json={"name": "Gram", "symbol": "g"}
    ).get_json()["data"]
    ingredient = client.post(
        "/api/v1/ingredients",
        headers=admin_headers,
        json={
            "name": "Coffee Beans",
            "unit_id": unit["id"],
            "min_stock": 2,
            "last_purchase_price": 100
        }
    ).get_json()["data"]

    purchase_payload = {
        "idempotency_key": "inventory-purchase-001",
        "items": [{
            "ingredient_id": ingredient["id"],
            "quantity": 10,
            "unit_price": 100
        }]
    }
    purchase = client.post(
        "/api/v1/purchases",
        headers=admin_headers,
        json=purchase_payload
    )
    purchase_retry = client.post(
        "/api/v1/purchases",
        headers=admin_headers,
        json=purchase_payload
    )
    assert purchase.status_code == 201
    assert purchase_retry.status_code == 200
    assert purchase_retry.get_json()["data"]["id"] == purchase.get_json()["data"]["id"]

    menu_id = client.get(
        "/api/v1/public/qr/test-token-meja-1/menu"
    ).get_json()["data"]["categories"][0]["menus"][0]["id"]
    recipe = client.post(
        "/api/v1/recipes",
        headers=admin_headers,
        json={
            "menu_id": menu_id,
            "items": [{
                "ingredient_id": ingredient["id"],
                "quantity": 2
            }]
        }
    )
    assert recipe.status_code == 200

    insufficient = client.post(
        "/api/v1/orders",
        headers=cashier_headers,
        json={
            "idempotency_key": "inventory-insufficient-order-001",
            "order_type": "TAKE_AWAY",
            "items": [{
                "menu_id": menu_id,
                "item_name": "Espresso",
                "quantity": 6,
                "unit_price": 10000
            }]
        }
    )
    assert insufficient.status_code == 409

    order = client.post(
        "/api/v1/orders",
        headers=cashier_headers,
        json={
            "idempotency_key": "inventory-sale-order-001",
            "order_type": "TAKE_AWAY",
            "items": [{
                "menu_id": menu_id,
                "item_name": "Espresso",
                "quantity": 2,
                "unit_price": 10000
            }]
        }
    )
    assert order.status_code == 201
    order_id = order.get_json()["data"]["id"]
    with client.application.app_context():
        assert StockBalance.query.filter_by(
            ingredient_id=ingredient["id"]
        ).one().current_stock == 6

    voided = client.post(
        f"/api/v1/orders/{order_id}/void",
        headers=cashier_headers,
        json={"admin_pin": "123456", "reason": "Test reversal"}
    )
    assert voided.status_code == 200
    with client.application.app_context():
        assert StockBalance.query.filter_by(
            ingredient_id=ingredient["id"]
        ).one().current_stock == 10

    overdraw = client.post(
        "/api/v1/stock/movements",
        headers=admin_headers,
        json={
            "idempotency_key": "inventory-overdraw-001",
            "ingredient_id": ingredient["id"],
            "type": "ADJUSTMENT",
            "quantity": -11
        }
    )
    assert overdraw.status_code == 409
    balances = client.get(
        "/api/v1/inventory/stock-balances",
        headers=admin_headers
    )
    assert balances.get_json()["data"][0]["current_stock"] == 10.0


def test_revoking_device_invalidates_existing_tokens(client):
    admin_headers = _login(client, "admin", "admin123")
    cashier_headers = _login(client, "kasir", "kasir123")

    with client.application.app_context():
        device = Device.query.filter_by(device_id="TEST_KASIR").one()
        device_id = device.id

    revoked = client.delete(
        f"/api/v1/devices/{device_id}",
        headers=admin_headers
    )
    assert revoked.status_code == 200

    sync_response = client.get(
        "/api/v1/sync/pull",
        headers=cashier_headers
    )
    assert sync_response.status_code == 401


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


def test_catalog_admin_can_manage_variants_modifiers_and_channel_prices(client):
    admin_headers = _login(client, "admin", "admin123")
    cashier_headers = _login(client, "kasir", "kasir123")
    category_id = client.get(
        "/api/v1/categories",
        headers=admin_headers
    ).get_json()["data"][0]["id"]

    menu_response = client.post(
        "/api/v1/menus",
        headers=admin_headers,
        json={
            "name": "Cold Brew",
            "category_id": category_id,
            "base_price": 15000,
        }
    )
    assert menu_response.status_code == 201
    menu_id = menu_response.get_json()["data"]["id"]

    variant_response = client.post(
        f"/api/v1/menus/{menu_id}/variants",
        headers=admin_headers,
        json={"name": "Large", "price_adjustment": 5000}
    )
    assert variant_response.status_code == 201
    variant_id = variant_response.get_json()["data"]["id"]

    forbidden_group = client.post(
        "/api/v1/modifier-groups",
        headers=cashier_headers,
        json={"name": "Milk"}
    )
    assert forbidden_group.status_code == 403

    group_response = client.post(
        "/api/v1/modifier-groups",
        headers=admin_headers,
        json={"name": "Milk", "min_selection": 0, "max_selection": 1}
    )
    assert group_response.status_code == 201
    group_id = group_response.get_json()["data"]["id"]
    modifier_response = client.post(
        f"/api/v1/modifier-groups/{group_id}/modifiers",
        headers=admin_headers,
        json={"name": "Oat Milk", "price": 4000}
    )
    assert modifier_response.status_code == 201

    channel_response = client.post(
        "/api/v1/channels",
        headers=admin_headers,
        json={"name": "GoFood", "code": "GOFOOD", "commission_percent": 20}
    )
    assert channel_response.status_code == 201
    channel_id = channel_response.get_json()["data"]["id"]

    price_response = client.post(
        f"/api/v1/channels/{channel_id}/menu-prices",
        headers=admin_headers,
        json={"menu_id": menu_id, "price": 20000}
    )
    assert price_response.status_code == 201
    retry_price = client.post(
        f"/api/v1/channels/{channel_id}/menu-prices",
        headers=admin_headers,
        json={"menu_id": menu_id, "price": 21000}
    )
    assert retry_price.status_code == 200

    catalog = client.get(
        "/api/v1/menus/catalog",
        headers=cashier_headers
    ).get_json()["data"]
    cold_brew = next(
        menu for category in catalog["categories"] for menu in category["menus"]
        if menu["id"] == menu_id
    )
    assert cold_brew["channel_prices"][channel_id] == 21000.0
    assert cold_brew["variants"][0]["id"] == variant_id
    assert catalog["modifier_groups"][0]["name"] == "Milk"

    deleted_variant = client.delete(
        f"/api/v1/variants/{variant_id}",
        headers=admin_headers
    )
    assert deleted_variant.status_code == 200


def test_sync_push_is_idempotent_and_pull_uses_server_cursor(client):
    headers = _login(client, "kasir", "kasir123")
    batch = [
        {
            "idempotency_key": "sync-change-001",
            "entity": "orders",
            "operation": "INSERT",
            "payload": {"id": "offline-order-001", "total": "12500.00"},
            "client_timestamp": "2020-01-01T00:00:00Z",
        },
        {
            "idempotency_key": "sync-change-002",
            "entity": "orders",
            "operation": "INSERT",
            "payload": {"id": "offline-order-002", "total": "8000.00"},
            "client_timestamp": "2020-01-01T00:00:00Z",
        },
    ]

    pushed = client.post(
        "/api/v1/sync/push",
        headers=headers,
        json={"batch": batch}
    )
    assert pushed.status_code == 200
    pushed_items = pushed.get_json()["data"]["items"]
    assert pushed.get_json()["data"]["processed"] == 2
    assert all(item["time_drift_detected"] for item in pushed_items)

    retried = client.post(
        "/api/v1/sync/push",
        headers=headers,
        json={"batch": batch}
    )
    assert retried.status_code == 200
    retry_items = retried.get_json()["data"]["items"]
    assert retried.get_json()["data"]["duplicates"] == 2
    assert [item["server_version"] for item in retry_items] == [
        item["server_version"] for item in pushed_items
    ]

    first_page = client.get(
        f"/api/v1/sync/pull?cursor={pushed_items[0]['server_version'] - 1}&limit=1",
        headers=headers
    )
    assert first_page.status_code == 200
    assert first_page.get_json()["data"]["has_more"] is True
    assert first_page.get_json()["data"]["changes"][0]["entity_id"] == "offline-order-001"

    second_page = client.get(
        f"/api/v1/sync/pull?cursor={first_page.get_json()['data']['cursor']}&limit=1",
        headers=headers
    )
    assert second_page.get_json()["data"]["has_more"] is False
    assert second_page.get_json()["data"]["changes"][0]["entity_id"] == "offline-order-002"


def test_sync_rejects_reused_key_with_different_payload_and_invalid_cursor(client):
    headers = _login(client, "kasir", "kasir123")
    original = {
        "idempotency_key": "sync-conflict-001",
        "entity": "orders",
        "operation": "INSERT",
        "payload": {"id": "offline-order-conflict", "total": "1000.00"},
    }
    accepted = client.post(
        "/api/v1/sync/push",
        headers=headers,
        json={"batch": [original]}
    )
    assert accepted.status_code == 200

    conflicting = dict(original, payload={
        "id": "offline-order-conflict",
        "total": "2000.00",
    })
    rejected = client.post(
        "/api/v1/sync/push",
        headers=headers,
        json={"batch": [conflicting]}
    )
    assert rejected.status_code == 409

    invalid_cursor = client.get(
        "/api/v1/sync/pull?cursor=-1",
        headers=headers
    )
    assert invalid_cursor.status_code == 400


def test_sync_push_keeps_first_order_insert_for_conflicting_ids(client):
    headers = _login(client, "kasir", "kasir123")
    first = {
        "idempotency_key": "sync-order-first-001",
        "entity": "orders",
        "operation": "INSERT",
        "payload": {"id": "offline-order-collision", "total": "1000.00"},
    }
    initial = client.post(
        "/api/v1/sync/push",
        headers=headers,
        json={"batch": [first]}
    )
    assert initial.status_code == 200
    initial_item = initial.get_json()["data"]["items"][0]

    conflicting = {
        "idempotency_key": "sync-order-second-001",
        "entity": "orders",
        "operation": "INSERT",
        "payload": {"id": "offline-order-collision", "total": "2000.00"},
    }
    rejected = client.post(
        "/api/v1/sync/push",
        headers=headers,
        json={"batch": [conflicting]}
    )

    assert rejected.status_code == 200
    result = rejected.get_json()["data"]["items"][0]
    assert result["status"] == "CONFLICT_SERVER_WINS"
    assert result["server_version"] == initial_item["server_version"]
    assert result["payload"]["total"] == "1000.00"


def test_server_model_changes_are_available_in_sync_pull(client):
    admin_headers = _login(client, "admin", "admin123")
    response = client.post(
        "/api/v1/categories",
        headers=admin_headers,
        json={"name": "Sync Test Category"}
    )
    assert response.status_code == 201
    category_id = response.get_json()["data"]["id"]

    with client.application.app_context():
        category = Category.query.filter_by(id=category_id).one()
        server_version = category.server_version

    assert server_version is not None
    pulled = client.get(
        f"/api/v1/sync/pull?cursor={server_version - 1}",
        headers=admin_headers
    )
    assert pulled.status_code == 200
    change = pulled.get_json()["data"]["changes"][0]
    assert change["entity"] == "categories"
    assert change["entity_id"] == category_id
    assert change["payload"]["server_version"] == server_version


def test_sync_push_keeps_master_data_server_authoritative(client):
    headers = _login(client, "admin", "admin123")
    category_id = client.get(
        "/api/v1/categories",
        headers=headers
    ).get_json()["data"][0]["id"]

    response = client.post(
        "/api/v1/sync/push",
        headers=headers,
        json={
            "batch": [{
                "idempotency_key": "sync-master-conflict-001",
                "entity": "categories",
                "operation": "UPDATE",
                "payload": {"id": category_id, "name": "Client Name"},
            }]
        }
    )

    assert response.status_code == 200
    item = response.get_json()["data"]["items"][0]
    assert item["status"] == "CONFLICT_SERVER_WINS"
    assert item["payload"]["name"] == "Coffee"
    assert item["server_version"] is not None


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


def test_pos_order_requires_idempotency_and_supports_order_queries(client):
    headers = _login(client, "kasir", "kasir123")
    menu_id = client.get(
        "/api/v1/public/qr/test-token-meja-1/menu"
    ).get_json()["data"]["categories"][0]["menus"][0]["id"]
    payload = {
        "order_type": "TAKE_AWAY",
        "items": [{
            "menu_id": menu_id,
            "item_name": "Espresso",
            "quantity": 1,
            "unit_price": 10000,
        }]
    }

    missing_key = client.post("/api/v1/orders", headers=headers, json=payload)
    assert missing_key.status_code == 400

    payload["idempotency_key"] = "pos-query-order-001"
    created = client.post("/api/v1/orders", headers=headers, json=payload)
    assert created.status_code == 201
    order_id = created.get_json()["data"]["id"]

    detail = client.get(f"/api/v1/orders/{order_id}", headers=headers)
    filtered = client.get(
        "/api/v1/orders?status=APPROVED&limit=10",
        headers=headers
    )
    assert detail.status_code == 200
    assert detail.get_json()["data"]["items"][0]["item_name"] == "Espresso"
    assert filtered.status_code == 200
    assert any(order["id"] == order_id for order in filtered.get_json()["data"])


def test_qris_static_payment_is_idempotent_and_audited(client):
    headers = _login(client, "kasir", "kasir123")
    menu_id = client.get(
        "/api/v1/public/qr/test-token-meja-1/menu"
    ).get_json()["data"]["categories"][0]["menus"][0]["id"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "idempotency_key": "qris-audit-order-001",
            "order_type": "TAKE_AWAY",
            "items": [{
                "menu_id": menu_id,
                "item_name": "Espresso",
                "quantity": 1,
                "unit_price": 10000,
            }]
        }
    )
    order_id = order.get_json()["data"]["id"]

    missing_key = client.post(
        f"/api/v1/orders/{order_id}/payments",
        headers=headers,
        json={"payment_method": "QRIS_STATIC", "amount": 10000}
    )
    assert missing_key.status_code == 400

    payment_payload = {
        "idempotency_key": "qris-audit-payment-001",
        "payment_method": "QRIS_STATIC",
        "amount": 10000,
    }
    first = client.post(
        f"/api/v1/orders/{order_id}/payments",
        headers=headers,
        json=payment_payload
    )
    retry = client.post(
        f"/api/v1/orders/{order_id}/payments",
        headers=headers,
        json=payment_payload
    )

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.get_json()["data"]["id"] == first.get_json()["data"]["id"]
    with client.application.app_context():
        assert Payment.query.filter_by(order_id=order_id).count() == 1
        assert AuditLog.query.filter_by(
            entity_id=order_id,
            action="QRIS_STATIC_PAYMENT"
        ).count() == 1


def test_large_order_discount_requires_admin_approval_token(client):
    headers = _login(client, "kasir", "kasir123")
    menu_id = client.get(
        "/api/v1/public/qr/test-token-meja-1/menu"
    ).get_json()["data"]["categories"][0]["menus"][0]["id"]
    payload = {
        "idempotency_key": "discount-approval-order-001",
        "order_type": "TAKE_AWAY",
        "discount": 1500,
        "items": [{
            "menu_id": menu_id,
            "item_name": "Espresso",
            "quantity": 1,
            "unit_price": 10000,
        }]
    }

    rejected = client.post("/api/v1/orders", headers=headers, json=payload)
    assert rejected.status_code == 403

    verification = client.post(
        "/api/v1/auth/verify-pin",
        headers=headers,
        json={"pin": "123456", "role": "admin"}
    )
    assert verification.status_code == 200
    payload["discount_approval_token"] = (
        verification.get_json()["data"]["approval_token"]
    )
    approved = client.post("/api/v1/orders", headers=headers, json=payload)

    assert approved.status_code == 201
    assert approved.get_json()["data"]["total"] == 8500.0
    with client.application.app_context():
        assert AuditLog.query.filter_by(
            entity_id=approved.get_json()["data"]["id"],
            action="ORDER_DISCOUNT_APPROVED"
        ).count() == 1


def test_delivery_order_uses_channel_price_and_reports_net_commission(client):
    admin_headers = _login(client, "admin", "admin123")
    cashier_headers = _login(client, "kasir", "kasir123")
    menu_id = client.get(
        "/api/v1/public/qr/test-token-meja-1/menu"
    ).get_json()["data"]["categories"][0]["menus"][0]["id"]
    channel = client.post(
        "/api/v1/channels",
        headers=admin_headers,
        json={
            "name": "Delivery Partner",
            "code": "DELIVERY_TEST",
            "commission_percent": 20
        }
    ).get_json()["data"]
    price = client.post(
        f"/api/v1/channels/{channel['id']}/menu-prices",
        headers=admin_headers,
        json={"menu_id": menu_id, "price": 15000}
    )
    assert price.status_code == 201

    payload = {
        "idempotency_key": "platform-order-001",
        "order_type": "DELIVERY",
        "channel_id": channel["id"],
        "external_order_id": "PARTNER-ORDER-001",
        "items": [{
            "menu_id": menu_id,
            "item_name": "Client Name",
            "quantity": 1,
            "unit_price": 1
        }]
    }
    created = client.post("/api/v1/orders", headers=cashier_headers, json=payload)
    assert created.status_code == 201
    order_id = created.get_json()["data"]["id"]
    assert created.get_json()["data"]["total"] == 15000.0

    retry = client.post(
        "/api/v1/orders",
        headers=cashier_headers,
        json=dict(payload, idempotency_key="platform-order-002")
    )
    assert retry.status_code == 200
    assert retry.get_json()["data"]["id"] == order_id

    with client.application.app_context():
        order = db.session.get(Order, order_id)
        cashier_id = User.query.filter_by(username="kasir").one().id
        assert order.platform_commission == 3000
        assert order.payments[0].payment_method == "PLATFORM"

    report = client.get(
        "/api/v1/reports/sales"
        f"?order_type=DELIVERY&channel_id={channel['id']}"
        f"&payment_method=PLATFORM&cashier_id={cashier_id}",
        headers=cashier_headers
    )
    summary = report.get_json()["data"]["summary"]
    assert report.status_code == 200
    assert summary["order_count"] == 1
    assert summary["total_platform_commission"] == 3000.0
    assert summary["total_net"] == 12000.0

    charts = client.get("/api/v1/reports/charts", headers=cashier_headers)
    assert charts.status_code == 200
    assert charts.get_json()["data"]["sales_by_day"]
    assert charts.get_json()["data"]["sales_by_hour"]
    assert charts.get_json()["data"]["sales_by_channel"]
    invalid_date = client.get(
        "/api/v1/reports/sales?start_date=not-a-date",
        headers=cashier_headers
    )
    assert invalid_date.status_code == 400


def test_profit_report_is_restricted_to_admin_roles(client):
    cashier_headers = _login(client, "kasir", "kasir123")
    admin_headers = _login(client, "admin", "admin123")

    forbidden = client.get("/api/v1/reports/profit", headers=cashier_headers)
    allowed = client.get("/api/v1/reports/profit", headers=admin_headers)

    assert forbidden.status_code == 403
    assert allowed.status_code == 200


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


def test_qr_order_idempotency_returns_existing_order(client):
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    payload = {
        "payment_method": "TUNAI",
        "items": [{"menu_id": menu["categories"][0]["menus"][0]["id"], "quantity": 1}]
    }
    headers = {"Idempotency-Key": "qr-order-retry-1"}

    first = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json=payload,
        headers=headers
    )
    retry = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json=payload,
        headers=headers
    )

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.get_json()["data"]["order_id"] == first.get_json()["data"]["order_id"]
    with client.application.app_context():
        assert Order.query.filter_by(idempotency_key=headers["Idempotency-Key"]).count() == 1


def test_qr_order_rate_limit_returns_json_error(client):
    client.application.config["QR_ORDER_RATE_LIMIT"] = "2 per minute"
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    payload = {
        "payment_method": "TUNAI",
        "items": [{"menu_id": menu["categories"][0]["menus"][0]["id"], "quantity": 1}]
    }

    responses = [
        client.post(
            "/api/v1/public/qr/test-token-meja-1/orders",
            json=payload,
            headers={"Idempotency-Key": f"qr-rate-{index}"}
        )
        for index in range(3)
    ]

    assert [response.status_code for response in responses] == [201, 201, 429]
    assert responses[2].get_json()["success"] is False


def test_qr_order_rate_limit_is_also_scoped_to_table(client):
    client.application.config["QR_ORDER_RATE_LIMIT"] = "10 per minute"
    client.application.config["QR_ORDER_TABLE_RATE_LIMIT"] = "1 per minute"
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    payload = {
        "payment_method": "TUNAI",
        "items": [{"menu_id": menu["categories"][0]["menus"][0]["id"], "quantity": 1}]
    }

    first = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json=payload,
        headers={"Idempotency-Key": "qr-table-rate-1"},
        environ_base={"REMOTE_ADDR": "192.0.2.10"}
    )
    second = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json=payload,
        headers={"Idempotency-Key": "qr-table-rate-2"},
        environ_base={"REMOTE_ADDR": "192.0.2.11"}
    )

    assert first.status_code == 201
    assert second.status_code == 429


def test_fcm_token_registration_is_bound_to_authenticated_device(client):
    headers = _login(client, "kasir", "kasir123")
    response = client.post(
        "/api/v1/devices/fcm-token",
        headers=headers,
        json={"token": "test-fcm-registration-token"}
    )

    assert response.status_code == 200
    with client.application.app_context():
        device = Device.query.filter_by(device_id="TEST_KASIR").one()
        assert device.fcm_token == "test-fcm-registration-token"

    invalid = client.post(
        "/api/v1/devices/fcm-token",
        headers=headers,
        json={"token": " "}
    )
    assert invalid.status_code == 400


def test_qr_order_persists_when_notifications_fail(client, monkeypatch):
    def fail_notification(*args, **kwargs):
        raise RuntimeError("notification service unavailable")

    monkeypatch.setattr("app.public.routes.socketio.emit", fail_notification)
    monkeypatch.setattr("app.public.routes.send_qr_order_notification", fail_notification)
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "TUNAI",
            "items": [{
                "menu_id": menu["categories"][0]["menus"][0]["id"],
                "quantity": 1
            }]
        }
    )

    assert response.status_code == 201
    with client.application.app_context():
        order = db.session.get(Order, response.get_json()["data"]["order_id"])
        assert order is not None
        assert order.status == STATUS_PENDING_APPROVAL


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
    payment_response = client.post(
        f"/api/v1/public/orders/{order_id}/create-payment"
    )
    assert payment_response.status_code == 503
    assert payment_response.get_json()["success"] is False


def test_qris_payment_creation_rejects_insufficient_recipe_stock(client, monkeypatch):
    with client.application.app_context():
        menu = Menu.query.one()
        unit = Unit(name="Gram", symbol="g")
        db.session.add(unit)
        db.session.flush()
        ingredient = Ingredient(name="Coffee bean", unit_id=unit.id)
        db.session.add(ingredient)
        db.session.flush()
        recipe = Recipe(menu_id=menu.id)
        db.session.add(recipe)
        db.session.flush()
        db.session.add(RecipeItem(
            recipe_id=recipe.id,
            ingredient_id=ingredient.id,
            quantity=1
        ))
        db.session.add(StockBalance(
            ingredient_id=ingredient.id,
            current_stock=0
        ))
        db.session.commit()

    menu_data = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    order = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "QRIS",
            "items": [{
                "menu_id": menu_data["categories"][0]["menus"][0]["id"],
                "quantity": 1
            }]
        }
    )
    order_id = order.get_json()["data"]["order_id"]
    client.application.config["PAYMENT_GATEWAY_SERVER_KEY"] = "test-server-key"

    def no_existing_gateway_order(method, path, payload=None):
        assert method == "GET"
        raise PaymentGatewayError("Belum ada tagihan", status_code=404)

    monkeypatch.setattr("app.public.routes._midtrans_request", no_existing_gateway_order)
    response = client.post(f"/api/v1/public/orders/{order_id}/create-payment")

    assert response.status_code == 409
    assert "Stok bahan" in response.get_json()["message"]


def test_qris_payment_reserves_stock_until_gateway_settles(client, monkeypatch):
    with client.application.app_context():
        menu = Menu.query.one()
        unit = Unit(name="Gram", symbol="g")
        db.session.add(unit)
        db.session.flush()
        ingredient = Ingredient(name="Coffee bean", unit_id=unit.id)
        db.session.add(ingredient)
        db.session.flush()
        recipe = Recipe(menu_id=menu.id)
        db.session.add(recipe)
        db.session.flush()
        db.session.add(RecipeItem(
            recipe_id=recipe.id,
            ingredient_id=ingredient.id,
            quantity=1
        ))
        db.session.add(StockBalance(
            ingredient_id=ingredient.id,
            current_stock=5
        ))
        db.session.commit()
        ingredient_id = ingredient.id

    menu_data = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    order_response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "QRIS",
            "items": [{
                "menu_id": menu_data["categories"][0]["menus"][0]["id"],
                "quantity": 2
            }]
        }
    )
    order_id = order_response.get_json()["data"]["order_id"]
    order_no = order_response.get_json()["data"]["order_no"]
    client.application.config["PAYMENT_GATEWAY_SERVER_KEY"] = "test-server-key"
    status_calls = 0

    def fake_gateway_request(method, path, payload=None):
        nonlocal status_calls
        if method == "POST":
            return {"qr_string": "MIDTRANS-QR-PAYLOAD"}
        status_calls += 1
        if status_calls == 1:
            raise PaymentGatewayError("Belum ada tagihan", status_code=404)
        return {
            "order_id": order_no,
            "gross_amount": "20000.00",
            "transaction_status": "settlement",
            "transaction_id": "reserved-transaction-1"
        }

    monkeypatch.setattr("app.public.routes._midtrans_request", fake_gateway_request)
    charge = client.post(f"/api/v1/public/orders/{order_id}/create-payment")
    with client.application.app_context():
        balance = StockBalance.query.filter_by(ingredient_id=ingredient_id).one()
        assert balance.current_stock == 3

    polled = client.post(f"/api/v1/public/orders/{order_id}/poll-payment")

    assert charge.status_code == 200
    assert polled.status_code == 200
    with client.application.app_context():
        balance = StockBalance.query.filter_by(ingredient_id=ingredient_id).one()
        assert balance.current_stock == 3
        assert db.session.get(Order, order_id).status == STATUS_APPROVED


def test_qris_payment_polling_processes_settlement_idempotently(client, monkeypatch):
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    order_response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "QRIS",
            "items": [{
                "menu_id": menu["categories"][0]["menus"][0]["id"],
                "quantity": 1
            }]
        }
    )
    order_id = order_response.get_json()["data"]["order_id"]
    order_no = order_response.get_json()["data"]["order_no"]
    client.application.config["PAYMENT_GATEWAY_SERVER_KEY"] = "test-server-key"
    monkeypatch.setattr(
        "app.public.routes._midtrans_request",
        lambda method, path, payload=None: {
            "order_id": order_no,
            "gross_amount": "10000.00",
            "transaction_status": "settlement",
            "transaction_id": "poll-transaction-1"
        }
    )

    response = client.post(f"/api/v1/public/orders/{order_id}/poll-payment")
    retry = client.post(f"/api/v1/public/orders/{order_id}/poll-payment")

    assert response.status_code == 200
    assert retry.status_code == 200
    with client.application.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == STATUS_APPROVED
        assert order.payment_status == "PAID"
        assert Payment.query.filter_by(order_id=order_id).count() == 1


def test_gateway_expiration_marks_order_expired(client, monkeypatch):
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    with client.application.app_context():
        menu_item = Menu.query.one()
        unit = Unit(name="Gram", symbol="g")
        db.session.add(unit)
        db.session.flush()
        ingredient = Ingredient(name="Coffee bean", unit_id=unit.id)
        db.session.add(ingredient)
        db.session.flush()
        recipe = Recipe(menu_id=menu_item.id)
        db.session.add(recipe)
        db.session.flush()
        db.session.add(RecipeItem(
            recipe_id=recipe.id,
            ingredient_id=ingredient.id,
            quantity=1
        ))
        db.session.add(StockBalance(
            ingredient_id=ingredient.id,
            current_stock=5
        ))
        db.session.commit()
        ingredient_id = ingredient.id
    order_response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "QRIS",
            "items": [{
                "menu_id": menu["categories"][0]["menus"][0]["id"],
                "quantity": 1
            }]
        }
    )
    order_id = order_response.get_json()["data"]["order_id"]
    order_no = order_response.get_json()["data"]["order_no"]
    client.application.config["PAYMENT_GATEWAY_SERVER_KEY"] = "test-server-key"

    status_calls = 0

    def fake_request(method, path, payload=None):
        nonlocal status_calls
        if method == "POST":
            return {"qr_string": "MIDTRANS-QR-PAYLOAD"}
        status_calls += 1
        if status_calls == 1:
            raise PaymentGatewayError("Belum ada tagihan", status_code=404)
        return {
            "order_id": order_no,
            "gross_amount": "10000.00",
            "transaction_status": "expire",
            "transaction_id": "expired-transaction-1"
        }

    monkeypatch.setattr(
        "app.public.routes._midtrans_request",
        fake_request
    )
    charge = client.post(f"/api/v1/public/orders/{order_id}/create-payment")
    assert charge.status_code == 200
    callback = {
        "order_id": order_no,
        "status_code": "200",
        "gross_amount": "10000.00",
        "transaction_status": "expire",
        "transaction_id": "expired-transaction-1"
    }
    callback["signature_key"] = hashlib.sha512(
        f"{order_no}20010000.00test-server-key".encode()
    ).hexdigest()

    response = client.post("/api/v1/public/payments/webhook", json=callback)

    assert response.status_code == 200
    with client.application.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == STATUS_EXPIRED
        assert order.payment_status == "UNPAID"
        assert Payment.query.filter_by(order_id=order_id).count() == 0
        balance = StockBalance.query.filter_by(ingredient_id=ingredient_id).one()
        assert balance.current_stock == 5


def test_invalid_gateway_signature_is_rejected_before_provider_lookup(client, monkeypatch):
    menu = client.get("/api/v1/public/qr/test-token-meja-1/menu").get_json()["data"]
    order_response = client.post(
        "/api/v1/public/qr/test-token-meja-1/orders",
        json={
            "payment_method": "QRIS",
            "items": [{
                "menu_id": menu["categories"][0]["menus"][0]["id"],
                "quantity": 1
            }]
        }
    )
    order_id = order_response.get_json()["data"]["order_id"]
    order_no = order_response.get_json()["data"]["order_no"]
    client.application.config["PAYMENT_GATEWAY_SERVER_KEY"] = "test-server-key"

    def unexpected_provider_call(*args, **kwargs):
        raise AssertionError("Invalid signatures must not call the gateway")

    monkeypatch.setattr("app.public.routes._midtrans_request", unexpected_provider_call)
    response = client.post("/api/v1/public/payments/webhook", json={
        "order_id": order_no,
        "status_code": "200",
        "gross_amount": "10000.00",
        "transaction_status": "settlement",
        "transaction_id": "forged-transaction",
        "signature_key": "invalid"
    })

    assert response.status_code == 403
    with client.application.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == STATUS_AWAITING_PAYMENT


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
