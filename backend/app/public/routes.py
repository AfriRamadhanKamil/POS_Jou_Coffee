import hmac
import hashlib
import json
from base64 import b64encode
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote, urlsplit
from flask import Blueprint, request, current_app
from app.extensions import db, socketio
from app.common.response import api_response, error_response
from app.catalog.models import Category, Menu, MenuVariant, Modifier, ModifierGroup
from app.orders.models import (
    Table, Order, OrderItem, OrderItemModifier, Payment, OrderStatusLog,
    STATUS_AWAITING_PAYMENT, STATUS_PENDING_APPROVAL, STATUS_APPROVED,
    STATUS_REJECTED, STATUS_CANCELLED,
    PAYMENT_UNPAID, PAYMENT_PAID,
    SOURCE_QR, TYPE_DINE_IN, TYPE_TAKE_AWAY
)
from app.orders.routes import generate_order_number
from app.inventory.services import deduct_stock_for_order

public_bp = Blueprint("public", __name__, url_prefix="/api/v1/public")


class PaymentGatewayError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _midtrans_request(method, path, payload=None):
    server_key = current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY", "")
    if not server_key:
        raise PaymentGatewayError("Payment gateway belum dikonfigurasi")

    base_url = current_app.config.get(
        "PAYMENT_GATEWAY_BASE_URL",
        "https://api.sandbox.midtrans.com"
    ).rstrip("/")
    authorization = b64encode(f"{server_key}:".encode("utf-8")).decode("ascii")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    gateway_request = Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    )
    try:
        with urlopen(gateway_request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise PaymentGatewayError(
            f"Payment gateway menolak permintaan (HTTP {error.code})",
            status_code=error.code
        ) from error
    except (URLError, TimeoutError) as error:
        raise PaymentGatewayError("Payment gateway tidak dapat dihubungi") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaymentGatewayError("Respons payment gateway tidak valid") from error


def _midtrans_qr_image_data(action_url):
    base_url = current_app.config.get(
        "PAYMENT_GATEWAY_BASE_URL",
        "https://api.sandbox.midtrans.com"
    ).rstrip("/")
    configured = urlsplit(base_url)
    target = urlsplit(action_url or "")
    if (
        target.scheme != "https"
        or target.netloc != configured.netloc
        or not target.path.startswith("/v2/")
    ):
        raise PaymentGatewayError("Alamat QR dari payment gateway tidak valid")

    server_key = current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY", "")
    authorization = b64encode(f"{server_key}:".encode("utf-8")).decode("ascii")
    image_request = Request(
        action_url,
        headers={"Authorization": f"Basic {authorization}", "Accept": "image/png"}
    )
    try:
        with urlopen(image_request, timeout=10) as response:
            content_type = response.headers.get_content_type()
            image = response.read(1_000_001)
    except HTTPError as error:
        raise PaymentGatewayError(
            f"QR pembayaran tidak dapat diambil (HTTP {error.code})"
        ) from error
    except (URLError, TimeoutError) as error:
        raise PaymentGatewayError("QR pembayaran tidak dapat diambil") from error
    if content_type not in {"image/png", "image/jpeg"} or len(image) > 1_000_000:
        raise PaymentGatewayError("Format gambar QR dari payment gateway tidak valid")
    return f"data:{content_type};base64,{b64encode(image).decode('ascii')}"


def verify_table_token(token: str) -> Table:
    """Verifies table token against registered active tables."""
    return Table.query_active().filter_by(qr_token=token, is_active=True).first()


# ==================== GET MENU VIA QR ====================

@public_bp.route("/qr/<token>/menu", methods=["GET"])
def get_qr_menu(token):
    table = verify_table_token(token)
    if not table:
        return error_response("QR meja tidak valid atau meja tidak aktif", 404)

    categories = Category.query_active().filter_by(is_active=True).order_by(Category.sort_order).all()
    modifier_groups = ModifierGroup.query_active().all()

    catalog_data = {
        "table": {
            "id": table.id,
            "number": table.table_number,
            "name": table.name
        },
        "categories": [{
            "id": c.id,
            "name": c.name,
            "menus": [{
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "image_url": m.image_url,
                "base_price": float(m.base_price),
                "is_available": m.is_available,
                "variants": [{
                    "id": v.id,
                    "name": v.name,
                    "price_adjustment": float(v.price_adjustment)
                } for v in m.variants if v.deleted_at is None and v.is_active]
            } for m in c.menus if m.deleted_at is None and m.is_active]
        } for c in categories],
        "modifier_groups": [{
            "id": mg.id,
            "name": mg.name,
            "min_selection": mg.min_selection,
            "max_selection": mg.max_selection,
            "is_required": mg.is_required,
            "modifiers": [{
                "id": mod.id,
                "name": mod.name,
                "price": float(mod.price)
            } for mod in mg.modifiers if mod.deleted_at is None and mod.is_active]
        } for mg in modifier_groups]
    }

    return api_response(catalog_data)


# ==================== CREATE QR ORDER ====================

@public_bp.route("/qr/<token>/orders", methods=["POST"])
def create_qr_order(token):
    table = verify_table_token(token)
    if not table:
        return error_response("QR meja tidak valid", 404)

    data = request.get_json(silent=True) or {}
    customer_name = str(data.get("customer_name", "")).strip()
    order_type = str(data.get("order_type", TYPE_DINE_IN)).upper()
    payment_method = str(data.get("payment_method", "TUNAI")).upper()
    items_data = data.get("items", [])

    if order_type not in {TYPE_DINE_IN, TYPE_TAKE_AWAY}:
        return error_response("Tipe pesanan QR tidak valid", 400)
    if payment_method not in {"TUNAI", "QRIS"}:
        return error_response("Metode pembayaran tidak valid", 400)
    if order_type == TYPE_TAKE_AWAY and not customer_name:
        return error_response("Nama pelanggan wajib diisi untuk Take Away", 400)
    if len(customer_name) > 100:
        return error_response("Nama pelanggan maksimal 100 karakter", 400)
    if not isinstance(items_data, list) or not items_data or len(items_data) > 50:
        return error_response("Pilih minimal satu menu", 400)

    # Server check menu availability before creating order
    subtotal = Decimal("0.00")
    order_items = []
    for it in items_data:
        if not isinstance(it, dict):
            return error_response("Format item pesanan tidak valid", 400)
        menu_id = it.get("menu_id")
        menu = Menu.query_active().filter_by(id=menu_id, is_active=True).first()
        if not menu or not menu.is_available:
            return error_response(f"Menu '{it.get('item_name', 'terpilih')}' sedang habis", 400)

        try:
            qty = Decimal(str(it.get("quantity", 1)))
        except (InvalidOperation, TypeError, ValueError):
            return error_response("Kuantitas item tidak valid", 400)
        if not qty.is_finite() or qty <= 0 or qty > 999:
            return error_response("Kuantitas item harus antara 0 dan 999", 400)
        unit_price = menu.base_price
        variant = None

        if it.get("variant_id"):
            variant = MenuVariant.query_active().filter_by(
                id=it["variant_id"], menu_id=menu.id, is_active=True
            ).first()
            if not variant:
                return error_response("Varian menu tidak valid", 400)
            unit_price += variant.price_adjustment

        modifier_ids = it.get("modifier_ids", [])
        if not isinstance(modifier_ids, list) or len(modifier_ids) > 20:
            return error_response("Pilihan modifier tidak valid", 400)
        if any(not isinstance(mod_id, str) for mod_id in modifier_ids):
            return error_response("Pilihan modifier tidak valid", 400)
        if len(set(modifier_ids)) != len(modifier_ids):
            return error_response("Modifier yang sama tidak boleh dipilih berulang", 400)
        modifiers = []
        modifier_total = Decimal("0.00")
        for mod_id in modifier_ids:
            mod = Modifier.query_active().filter_by(id=mod_id, is_active=True).first()
            if not mod:
                return error_response("Modifier tidak valid", 400)
            modifiers.append(mod)
            modifier_total += mod.price

        item_subtotal = qty * (unit_price + modifier_total)
        subtotal += item_subtotal

        order_item = OrderItem(
            menu_id=menu.id,
            variant_id=variant.id if variant else None,
            item_name=menu.name + (f" ({variant.name})" if variant else ""),
            quantity=qty,
            unit_price=unit_price,
            discount=Decimal("0.00"),
            subtotal=item_subtotal,
            notes=it.get("notes")
        )

        for mod in modifiers:
            order_item.modifiers.append(OrderItemModifier(
                modifier_id=mod.id,
                modifier_name=mod.name,
                price=mod.price
            ))

        order_items.append(order_item)

    total = subtotal
    order_no = generate_order_number("QR01")

    # Initial status: QRIS -> AWAITING_PAYMENT, Tunai -> PENDING_APPROVAL
    if payment_method == "QRIS":
        status = STATUS_AWAITING_PAYMENT
    else:
        status = STATUS_PENDING_APPROVAL

    order = Order(
        order_no=order_no,
        source=SOURCE_QR,
        order_type=order_type,
        table_id=table.id if order_type == TYPE_DINE_IN else None,
        status=status,
        payment_status=PAYMENT_UNPAID,
        subtotal=subtotal,
        discount=Decimal("0.00"),
        total=total,
        customer_name=customer_name or ("Pelanggan Meja " + table.table_number),
        created_by="CUSTOMER_QR"
    )

    for oi in order_items:
        order.items.append(oi)

    db.session.add(order)
    db.session.flush()

    db.session.add(OrderStatusLog(
        order_id=order.id,
        to_status=status,
        notes="Pesanan QR dibuat oleh pelanggan"
    ))
    db.session.commit()

    # Notify cashiers if Tunai (requires cashier approval)
    if status == STATUS_PENDING_APPROVAL:
        socketio.emit("qr_order_pending", {
            "order_id": order.id,
            "order_no": order.order_no,
            "table_number": table.table_number,
            "customer_name": order.customer_name,
            "total": float(order.total)
        }, namespace="/ws")

    return api_response({
        "order_id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "total": float(order.total),
        "payment_method": payment_method
    }, "Pesanan QR berhasil dibuat", 201)


# ==================== CHECK ORDER STATUS ====================

@public_bp.route("/orders/<order_id>/status", methods=["GET"])
def check_order_status(order_id):
    order = Order.query.get(order_id)
    if not order:
        return error_response("Pesanan tidak ditemukan", 404)

    return api_response({
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "payment_status": order.payment_status,
        "customer_name": order.customer_name,
        "table_number": order.table.table_number if order.table else None,
        "total": float(order.total),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [{
            "item_name": item.item_name,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "subtotal": float(item.subtotal)
        } for item in order.items]
    })


# ==================== GENERATE QRIS CHARGE ====================

@public_bp.route("/orders/<order_id>/pay", methods=["POST"])
def generate_qris_payment(order_id):
    """
    Generate dynamic QRIS charge via payment gateway.
    Returns QR code payload/image URL for customer.
    """
    order = Order.query_active().filter_by(id=order_id, source=SOURCE_QR).first()
    if not order:
        return error_response("Pesanan tidak ditemukan", 404)

    if order.payment_status == PAYMENT_PAID:
        return error_response("Pesanan sudah dibayar", 400)
    if order.status != STATUS_AWAITING_PAYMENT:
        return error_response("Pesanan tidak menunggu pembayaran QRIS", 409)

    gateway_provider = current_app.config.get("PAYMENT_GATEWAY_PROVIDER", "midtrans")
    if gateway_provider != "midtrans":
        return error_response("Payment gateway yang dipilih belum didukung", 503)
    if not current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY"):
        return error_response("Payment gateway belum dikonfigurasi", 503)

    order_ref = quote(order.order_no, safe="")
    try:
        existing_transaction = _midtrans_request("GET", f"/v2/{order_ref}/status")
    except PaymentGatewayError as error:
        if error.status_code != 404:
            return error_response(str(error), 502)
        existing_transaction = None

    if existing_transaction:
        if not isinstance(existing_transaction, dict):
            return error_response("Respons payment gateway tidak valid", 502)
        try:
            existing_amount = Decimal(str(existing_transaction.get("gross_amount", "0")))
        except (InvalidOperation, TypeError, ValueError):
            return error_response("Respons payment gateway tidak valid", 502)
        if not existing_amount.is_finite() or existing_amount != order.total:
            return error_response("Nominal tagihan gateway tidak sesuai", 502)
        if existing_transaction.get("transaction_status") != "pending":
            return error_response("Tagihan QRIS tidak lagi menunggu pembayaran", 409)
        qr_url = (
            current_app.config.get("PAYMENT_GATEWAY_BASE_URL", "https://api.sandbox.midtrans.com")
            .rstrip("/")
            + f"/v2/{order_ref}/qr-code"
        )
        try:
            qr_image_data = _midtrans_qr_image_data(qr_url)
        except PaymentGatewayError as error:
            return error_response(str(error), 502)
        return api_response({
            "order_id": order.id,
            "order_no": order.order_no,
            "amount": float(order.total),
            "provider": gateway_provider,
            "qris_content": None,
            "qris_image_data": qr_image_data,
            "expires_at": existing_transaction.get("expiry_time"),
            "expires_in_minutes": 10
        }, "Tagihan QRIS aktif berhasil dimuat")

    try:
        charge = _midtrans_request("POST", "/v2/charge", {
            "payment_type": "qris",
            "transaction_details": {
                "order_id": order.order_no,
                "gross_amount": float(order.total)
            },
            "qris": {"acquirer": "gopay"},
            "customer_details": {"first_name": order.customer_name or "Pelanggan"}
        })
    except PaymentGatewayError as error:
        status_code = 503 if "belum dikonfigurasi" in str(error) else 502
        return error_response(str(error), status_code)

    if not isinstance(charge, dict):
        return error_response("Respons payment gateway tidak valid", 502)
    actions = charge.get("actions", [])
    if not isinstance(actions, list):
        actions = []
    qr_action = next(
        (
            action for action in actions
            if isinstance(action, dict)
            and action.get("name") in {"generate-qr-code", "generate-qr-code-v2"}
        ),
        None
    )
    qr_content = charge.get("qr_string")
    if not isinstance(qr_content, str):
        qr_content = None
    qr_image_url = qr_action.get("url") if qr_action else None
    qr_image_data = None
    if qr_image_url and not qr_content:
        try:
            qr_image_data = _midtrans_qr_image_data(qr_image_url)
        except PaymentGatewayError as error:
            return error_response(str(error), 502)
    if not qr_content and not qr_image_data:
        return error_response("Payment gateway tidak mengembalikan QRIS yang dapat ditampilkan", 502)

    return api_response({
        "order_id": order.id,
        "order_no": order.order_no,
        "amount": float(order.total),
        "provider": gateway_provider,
        "qris_content": qr_content,
        "qris_image_data": qr_image_data,
        "expires_at": charge.get("expiry_time"),
        "expires_in_minutes": 10
    }, "Tagihan QRIS dinamis berhasil dibuat")


# ==================== PAYMENT WEBHOOK ====================

@public_bp.route("/payments/webhook", methods=["POST"])
def payment_webhook():
    """
    Webhook callback from payment gateway (e.g., Midtrans / Xendit).
    Must be idempotent and signature-verified.
    """
    data = request.get_json(silent=True) or {}
    server_key = current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY", "")
    if not server_key:
        return error_response("Payment gateway belum dikonfigurasi", 503)

    # Midtrans style verification: SHA512(order_id + status_code + gross_amount + ServerKey)
    order_id_ref = data.get("order_id")
    status_code = data.get("status_code", "")
    gross_amount = data.get("gross_amount", "")
    signature_key = data.get("signature_key", "")
    transaction_status = data.get("transaction_status", "")

    # Check order
    if not all(isinstance(value, str) for value in (order_id_ref, status_code, gross_amount, signature_key)):
        return error_response("Data notifikasi pembayaran tidak valid", 400)

    order = Order.query_active().filter_by(
        order_no=order_id_ref,
        source=SOURCE_QR
    ).with_for_update().first()
    if not order:
        return error_response("Order not found", 404)

    raw_str = f"{order_id_ref}{status_code}{gross_amount}{server_key}"
    expected_sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()
    if not signature_key or not hmac.compare_digest(expected_sig, signature_key):
        return error_response("Invalid signature", 403)

    try:
        callback_amount = Decimal(gross_amount)
    except (InvalidOperation, TypeError, ValueError):
        return error_response("Nominal pembayaran tidak valid", 400)
    if not callback_amount.is_finite() or callback_amount != order.total:
        return error_response("Nominal pembayaran tidak sesuai dengan pesanan", 400)

    try:
        verified_status = _midtrans_request(
            "GET",
            f"/v2/{quote(order_id_ref, safe='')}/status"
        )
    except PaymentGatewayError as error:
        return error_response(str(error), 502)
    try:
        verified_amount = Decimal(str(verified_status.get("gross_amount", "0")))
    except (InvalidOperation, TypeError, ValueError):
        return error_response("Nominal dari payment gateway tidak valid", 502)
    if (
        verified_status.get("order_id") != order.order_no
        or not verified_amount.is_finite()
        or verified_amount != order.total
        or verified_status.get("transaction_status") != transaction_status
        or verified_status.get("transaction_id") != data.get("transaction_id")
    ):
        return error_response("Status pembayaran tidak cocok dengan data gateway", 403)

    # Idempotent check occurs only after authenticating the gateway notification.
    if order.payment_status == PAYMENT_PAID:
        return api_response(None, "Payment already processed (idempotent)")

    if order.status != STATUS_AWAITING_PAYMENT:
        return error_response("Pesanan tidak lagi menunggu pembayaran", 409)

    # Process successful payment (settlement or capture)
    is_successful = transaction_status == "settlement" or (
        transaction_status == "capture" and data.get("fraud_status") == "accept"
    )
    if is_successful:
        order.payment_status = PAYMENT_PAID
        order.status = STATUS_APPROVED
        order.approved_at = datetime.now(timezone.utc)

        # Record payment entry
        payment = Payment(
            order_id=order.id,
            payment_method="QRIS_DINAMIS",
            amount=callback_amount,
            change_amount=Decimal("0.00"),
            status=PAYMENT_PAID,
            provider="midtrans",
            provider_ref=data.get("transaction_id"),
            paid_at=datetime.now(timezone.utc),
            raw_webhook=request.get_data(as_text=True)
        )
        db.session.add(payment)

        # Deduct stock automatically on approval
        deduct_stock_for_order(order)

        db.session.add(OrderStatusLog(
            order_id=order.id,
            from_status=STATUS_AWAITING_PAYMENT,
            to_status=STATUS_APPROVED,
            notes="QRIS terverifikasi lewat webhook gateway"
        ))
        db.session.commit()

        # Realtime notify cashier to print kitchen ticket & receipt
        socketio.emit("qris_payment_received", {
            "order_id": order.id,
            "order_no": order.order_no,
            "total": float(order.total)
        }, namespace="/ws")

        return api_response(None, "Payment verified and order approved")

    return api_response(None, "Webhook received")
