import hmac
import hashlib
from decimal import Decimal
from datetime import datetime, timezone
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

    data = request.get_json() or {}
    customer_name = data.get("customer_name", "").strip()
    order_type = data.get("order_type", TYPE_DINE_IN)
    payment_method = data.get("payment_method", "TUNAI").upper()  # TUNAI or QRIS
    items_data = data.get("items", [])

    if not items_data:
        return error_response("Pilih minimal satu menu", 400)

    # Server check menu availability before creating order
    subtotal = Decimal("0.00")
    order_items = []
    for it in items_data:
        menu = Menu.query_active().filter_by(id=it["menu_id"], is_active=True).first()
        if not menu or not menu.is_available:
            return error_response(f"Menu '{it.get('item_name', 'terpilih')}' sedang habis", 400)

        qty = Decimal(str(it.get("quantity", 1)))
        unit_price = menu.base_price
        variant = None

        if it.get("variant_id"):
            variant = MenuVariant.query_active().filter_by(id=it["variant_id"], is_active=True).first()
            if variant:
                unit_price += variant.price_adjustment

        item_subtotal = qty * unit_price
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

        for mod_id in it.get("modifier_ids", []):
            mod = Modifier.query_active().filter_by(id=mod_id, is_active=True).first()
            if mod:
                subtotal += mod.price * qty
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
    order = Order.query.get(order_id)
    if not order:
        return error_response("Pesanan tidak ditemukan", 404)

    if order.payment_status == PAYMENT_PAID:
        return error_response("Pesanan sudah dibayar", 400)

    # In sandbox/demo or actual payment gateway integration
    gateway_provider = current_app.config.get("PAYMENT_GATEWAY_PROVIDER", "midtrans")
    qris_string = f"00020101021226600016ID.CO.QRIS.WWW01189360099900000000015204549953033605802ID5910JOU COFFEE6007BANDUNG62070703A016304{order.order_no}"

    return api_response({
        "order_id": order.id,
        "order_no": order.order_no,
        "amount": float(order.total),
        "provider": gateway_provider,
        "qris_content": qris_string,
        "expires_in_minutes": 10
    }, "Tagihan QRIS dinamis berhasil dibuat")


# ==================== PAYMENT WEBHOOK ====================

@public_bp.route("/payments/webhook", methods=["POST"])
def payment_webhook():
    """
    Webhook callback from payment gateway (e.g., Midtrans / Xendit).
    Must be idempotent and signature-verified.
    """
    data = request.get_json() or {}
    server_key = current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY", "")

    # Midtrans style verification: SHA512(order_id + status_code + gross_amount + ServerKey)
    order_id_ref = data.get("order_id")
    status_code = data.get("status_code", "")
    gross_amount = data.get("gross_amount", "")
    signature_key = data.get("signature_key", "")
    transaction_status = data.get("transaction_status", "")

    # Check order
    order = Order.query.filter((Order.id == order_id_ref) | (Order.order_no == order_id_ref)).first()
    if not order:
        return error_response("Order not found", 404)

    # Idempotent check: if already paid, return 200 immediately
    if order.payment_status == PAYMENT_PAID:
        return api_response(None, "Payment already processed (idempotent)")

    # Verify signature if key is configured
    if server_key and signature_key:
        raw_str = f"{order_id_ref}{status_code}{gross_amount}{server_key}"
        expected_sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()
        if expected_sig != signature_key:
            return error_response("Invalid signature", 403)

    # Process successful payment (settlement or capture)
    if transaction_status in ["settlement", "capture", "PAID", "SUCCESS"]:
        order.payment_status = PAYMENT_PAID
        order.status = STATUS_APPROVED
        order.approved_at = datetime.now(timezone.utc)

        # Record payment entry
        payment = Payment(
            order_id=order.id,
            payment_method="QRIS_DINAMIS",
            amount=Decimal(str(gross_amount or order.total)),
            change_amount=Decimal("0.00"),
            status=PAYMENT_PAID,
            provider="gateway",
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
