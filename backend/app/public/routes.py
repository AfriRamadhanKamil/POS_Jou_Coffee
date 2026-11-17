import hashlib
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from urllib.parse import quote
from flask import Blueprint, request, current_app
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import IntegrityError
from app.extensions import db, limiter, socketio
from app.common.response import api_response, error_response
from app.catalog.models import Category, Menu, MenuVariant, Modifier, ModifierGroup
from app.orders.models import (
    Table, Order, OrderItem, OrderItemModifier, Payment, OrderStatusLog,
    STATUS_AWAITING_PAYMENT, STATUS_PENDING_APPROVAL, STATUS_APPROVED,
    STATUS_REJECTED, STATUS_CANCELLED, STATUS_EXPIRED,
    PAYMENT_UNPAID, PAYMENT_PAID,
    SOURCE_QR, TYPE_DINE_IN, TYPE_TAKE_AWAY
)
from app.orders.routes import generate_order_number
from app.inventory.services import (
    deduct_stock_for_order,
    release_stock_reservation,
    reserve_stock_for_order
)
from app.realtime.push import send_cashier_notification, send_qr_order_notification
from app.inventory.services import InsufficientStockError
from app.payments.providers import PaymentGatewayError, get_payment_gateway_provider

public_bp = Blueprint("public", __name__, url_prefix="/api/v1/public")


def _midtrans_request(method, path, payload=None):
    return _get_payment_gateway().request(method, path, payload)


def _get_payment_gateway():
    return get_payment_gateway_provider(
        current_app.config.get("PAYMENT_GATEWAY_PROVIDER", "midtrans")
    )


def _gateway_unavailable(message, status_code=503):
    return api_response(
        {"fallback_payment_method": "TUNAI"},
        message,
        status_code,
        success=False
    )


def _midtrans_qr_image_data(action_url):
    return _get_payment_gateway().qr_image_data(action_url)


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
@limiter.limit(
    lambda: current_app.config["QR_ORDER_TABLE_RATE_LIMIT"],
    key_func=lambda: request.view_args["token"]
)
@limiter.limit(
    lambda: current_app.config["QR_ORDER_RATE_LIMIT"],
    key_func=get_remote_address
)
def create_qr_order(token):
    table = verify_table_token(token)
    if not table:
        return error_response("QR meja tidak valid", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Format pesanan tidak valid", 400)
    idempotency_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
    if idempotency_key is not None:
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key.strip()) > 64
        ):
            return error_response("Idempotency-Key tidak valid (maksimal 64 karakter)", 400)
        idempotency_key = idempotency_key.strip()
        existing = Order.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            if existing.source != SOURCE_QR or existing.table_id != table.id:
                return error_response("Idempotency-Key sudah digunakan untuk pesanan lain", 409)
            return api_response({
                "order_id": existing.id,
                "order_no": existing.order_no,
                "status": existing.status,
                "total": float(existing.total),
                "payment_method": (
                    "QRIS" if existing.status == STATUS_AWAITING_PAYMENT else "TUNAI"
                )
            }, "Pesanan QR sudah diproses (idempotent)")

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
        created_by="CUSTOMER_QR",
        idempotency_key=idempotency_key
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
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = (
            Order.query.filter_by(idempotency_key=idempotency_key).first()
            if idempotency_key else None
        )
        if existing and existing.source == SOURCE_QR and existing.table_id == table.id:
            return api_response({
                "order_id": existing.id,
                "order_no": existing.order_no,
                "status": existing.status,
                "total": float(existing.total),
                "payment_method": (
                    "QRIS" if existing.status == STATUS_AWAITING_PAYMENT else "TUNAI"
                )
            }, "Pesanan QR sudah diproses (idempotent)")
        raise

    # Notify cashiers if Tunai (requires cashier approval)
    if status == STATUS_PENDING_APPROVAL:
        notification = {
            "order_id": order.id,
            "order_no": order.order_no,
            "table_number": table.table_number,
            "customer_name": order.customer_name,
            "total": float(order.total)
        }
        try:
            socketio.emit("qr_order_pending", notification, namespace="/ws", to="orders")
        except Exception:
            current_app.logger.exception(
                "Failed to emit realtime notification for QR order %s", order.id
            )
        try:
            send_qr_order_notification(notification)
        except Exception:
            current_app.logger.exception(
                "Failed to notify cashier devices for QR order %s", order.id
            )

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

@public_bp.route("/orders/<order_id>/create-payment", methods=["POST"])
@public_bp.route("/orders/<order_id>/pay", methods=["POST"])
def generate_qris_payment(order_id):
    """
    Generate dynamic QRIS charge via payment gateway.
    Returns QR code payload/image URL for customer.
    """
    order = (
        Order.query_active()
        .filter_by(id=order_id, source=SOURCE_QR)
        .with_for_update()
        .first()
    )
    if not order:
        return error_response("Pesanan tidak ditemukan", 404)

    if order.payment_status == PAYMENT_PAID:
        return error_response("Pesanan sudah dibayar", 400)
    if order.status != STATUS_AWAITING_PAYMENT:
        return error_response("Pesanan tidak menunggu pembayaran QRIS", 409)

    try:
        gateway_provider = _get_payment_gateway()
    except PaymentGatewayError as error:
        return _gateway_unavailable(str(error))
    if not current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY"):
        return _gateway_unavailable("Payment gateway belum dikonfigurasi")

    try:
        existing_transaction = gateway_provider.get_status(
            order.order_no,
            _midtrans_request
        )
    except PaymentGatewayError as error:
        if error.status_code != 404:
            return _gateway_unavailable(str(error), 502)
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
            try:
                notification = gateway_provider.normalize_status(existing_transaction, order)
            except PaymentGatewayError as error:
                return error_response(str(error), error.status_code or 502)
            return _apply_gateway_status(order, gateway_provider, notification)
        qr_url = (
            current_app.config.get("PAYMENT_GATEWAY_BASE_URL", "https://api.sandbox.midtrans.com")
            .rstrip("/")
            + f"/v2/{quote(order.order_no, safe='')}/qr-code"
        )
        try:
            qr_image_data = _midtrans_qr_image_data(qr_url)
        except PaymentGatewayError as error:
            return _gateway_unavailable(str(error), 502)
        return api_response({
            "order_id": order.id,
            "order_no": order.order_no,
            "amount": float(order.total),
            "provider": gateway_provider.name,
            "qris_content": None,
            "qris_image_data": qr_image_data,
            "expires_at": existing_transaction.get("expiry_time"),
            "expires_in_minutes": 10
        }, "Tagihan QRIS aktif berhasil dimuat")

    try:
        reserve_stock_for_order(order)
    except InsufficientStockError as error:
        db.session.rollback()
        return error_response(str(error), 409)

    db.session.commit()
    try:
        charge = gateway_provider.create_qris_charge(order, _midtrans_request)
    except PaymentGatewayError as error:
        if error.status_code is None or error.status_code >= 500:
            return error_response(
                "Status tagihan belum dapat dipastikan; periksa status pembayaran sebelum mencoba lagi",
                502
            )
        release_stock_reservation(order)
        order.status = STATUS_EXPIRED
        db.session.add(OrderStatusLog(
            order_id=order.id,
            from_status=STATUS_AWAITING_PAYMENT,
            to_status=STATUS_EXPIRED,
            notes="Gateway menolak pembuatan tagihan"
        ))
        db.session.commit()
        return _gateway_unavailable(str(error), 503)

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
            return _gateway_unavailable(str(error), 502)
    if not qr_content and not qr_image_data:
        return _gateway_unavailable(
            "Payment gateway tidak mengembalikan QRIS yang dapat ditampilkan",
            502
        )

    return api_response({
        "order_id": order.id,
        "order_no": order.order_no,
        "amount": float(order.total),
        "provider": gateway_provider.name,
        "qris_content": qr_content,
        "qris_image_data": qr_image_data,
        "expires_at": charge.get("expiry_time"),
        "expires_in_minutes": 10
    }, "Tagihan QRIS dinamis berhasil dibuat")


def _apply_gateway_status(order, gateway_provider, notification, raw_webhook=None):
    transaction_status = notification["transaction_status"]
    if order.payment_status == PAYMENT_PAID:
        return api_response(None, "Payment already processed (idempotent)")
    if order.status == STATUS_EXPIRED and transaction_status in {"expire", "cancel", "deny"}:
        return api_response(None, "Payment expiration already processed (idempotent)")
    if order.status != STATUS_AWAITING_PAYMENT:
        return error_response("Pesanan tidak lagi menunggu pembayaran", 409)

    is_successful = transaction_status == "settlement" or (
        transaction_status == "capture" and notification["fraud_status"] == "accept"
    )
    if is_successful:
        now = datetime.now(timezone.utc)
        order.payment_status = PAYMENT_PAID
        order.status = STATUS_APPROVED
        order.approved_at = now
        db.session.add(Payment(
            order_id=order.id,
            payment_method="QRIS_DINAMIS",
            amount=notification["amount"],
            change_amount=Decimal("0.00"),
            status=PAYMENT_PAID,
            provider=gateway_provider.name,
            provider_ref=notification["transaction_id"],
            idempotency_key=hashlib.sha256(
                f"{gateway_provider.name}:{notification['transaction_id']}".encode("utf-8")
            ).hexdigest(),
            paid_at=now,
            raw_webhook=raw_webhook
        ))
        deduct_stock_for_order(order)
        db.session.add(OrderStatusLog(
            order_id=order.id,
            from_status=STATUS_AWAITING_PAYMENT,
            to_status=STATUS_APPROVED,
            notes="QRIS terverifikasi melalui payment gateway"
        ))
        db.session.commit()

        try:
            socketio.emit("qris_payment_received", {
                "order_id": order.id,
                "order_no": order.order_no,
                "total": float(order.total)
            }, namespace="/ws", to="orders")
        except Exception:
            current_app.logger.exception(
                "Failed to emit payment notification for QR order %s", order.id
            )
        try:
            send_cashier_notification(
                {
                    "order_id": order.id,
                    "order_no": order.order_no
                },
                "Pembayaran QRIS berhasil",
                f"Pesanan {order.order_no} sudah dibayar",
                "qris_payment_received"
            )
        except Exception:
            current_app.logger.exception(
                "Failed to send payment push notification for QR order %s", order.id
            )
        return api_response(None, "Payment verified and order approved")

    if transaction_status in {"expire", "cancel", "deny"}:
        order.status = STATUS_EXPIRED
        release_stock_reservation(order)
        db.session.add(OrderStatusLog(
            order_id=order.id,
            from_status=STATUS_AWAITING_PAYMENT,
            to_status=STATUS_EXPIRED,
            notes=f"Pembayaran gateway berstatus {transaction_status}"
        ))
        db.session.commit()
        return api_response(None, "Tagihan pembayaran sudah kedaluwarsa")

    return api_response({
        "status": order.status,
        "payment_status": order.payment_status
    }, "Pembayaran masih menunggu")


# ==================== PAYMENT WEBHOOK ====================

@public_bp.route("/payments/webhook", methods=["POST"])
def payment_webhook():
    """
    Webhook callback from payment gateway (e.g., Midtrans / Xendit).
    Must be idempotent and signature-verified.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Data notifikasi pembayaran tidak valid", 400)
    server_key = current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY", "")
    if not server_key:
        return error_response("Payment gateway belum dikonfigurasi", 503)

    try:
        gateway_provider = _get_payment_gateway()
        order_id_ref = gateway_provider.notification_order_reference(data)
        gateway_provider.verify_signature(data)
    except PaymentGatewayError as error:
        return error_response(str(error), error.status_code or 400)

    order = Order.query_active().filter_by(
        order_no=order_id_ref,
        source=SOURCE_QR
    ).with_for_update().first()
    if not order:
        return error_response("Order not found", 404)

    try:
        notification = gateway_provider.verify_notification(
            data,
            order,
            _midtrans_request
        )
    except PaymentGatewayError as error:
        return error_response(str(error), error.status_code or 502)

    return _apply_gateway_status(
        order,
        gateway_provider,
        notification,
        raw_webhook=request.get_data(as_text=True)
    )


@public_bp.route("/orders/<order_id>/poll-payment", methods=["POST"])
@limiter.limit("6 per minute")
def poll_qris_payment(order_id):
    order = (
        Order.query_active()
        .filter_by(id=order_id, source=SOURCE_QR)
        .with_for_update()
        .first()
    )
    if not order:
        return error_response("Pesanan tidak ditemukan", 404)
    if order.status != STATUS_AWAITING_PAYMENT:
        return api_response({
            "status": order.status,
            "payment_status": order.payment_status
        }, "Status pembayaran berhasil diperbarui")
    if not current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY"):
        return api_response(
            {"fallback_payment_method": "TUNAI"},
            "Payment gateway tidak tersedia; arahkan pelanggan ke pembayaran tunai",
            503,
            success=False
        )

    try:
        gateway_provider = _get_payment_gateway()
        gateway_status = gateway_provider.get_status(order.order_no, _midtrans_request)
        notification = gateway_provider.normalize_status(gateway_status, order)
    except PaymentGatewayError as error:
        if error.status_code == 404:
            return api_response({
                "status": order.status,
                "payment_status": order.payment_status,
                "fallback_payment_method": "TUNAI"
            }, "Tagihan gateway belum tersedia; pelanggan dapat memilih pembayaran tunai")
        status_code = error.status_code or 502
        return error_response(str(error), status_code)

    return _apply_gateway_status(order, gateway_provider, notification)
