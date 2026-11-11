from decimal import Decimal
from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db, socketio
from app.common.response import api_response, error_response
from app.common.auth import role_required, verify_password, ALL_ROLES, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.auth.models import User, AuditLog
from app.orders.models import (
    Order, OrderItem, OrderItemModifier, Payment, OrderStatusLog, Table,
    STATUS_AWAITING_PAYMENT, STATUS_PENDING_APPROVAL, STATUS_APPROVED,
    STATUS_PREPARING, STATUS_READY, STATUS_COMPLETED, STATUS_REJECTED,
    STATUS_EXPIRED, STATUS_CANCELLED,
    PAYMENT_UNPAID, PAYMENT_PAID, PAYMENT_REFUNDED,
    SOURCE_POS, SOURCE_QR, SOURCE_ONLINE,
    TYPE_DINE_IN, TYPE_TAKE_AWAY, TYPE_DELIVERY
)
from app.inventory.services import deduct_stock_for_order, return_stock_for_void

orders_bp = Blueprint("orders", __name__, url_prefix="/api/v1/orders")


def generate_order_number(device_id="K01"):
    """
    Format: JOU-{device_code}-{YYYYMMDD}-{sequence:04d}
    Example: JOU-K01-20261102-0007
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    dev_code = (device_id[-3:] if device_id else "K01").upper()
    prefix = f"JOU-{dev_code}-{date_str}-"

    # Find highest sequence today
    last_order = Order.query.filter(Order.order_no.like(f"{prefix}%")).order_by(Order.order_no.desc()).first()
    if last_order:
        last_seq = int(last_order.order_no.split("-")[-1])
        new_seq = last_seq + 1
    else:
        new_seq = 1

    return f"{prefix}{new_seq:04d}"


# ==================== CREATE ORDER (POS & ONLINE) ====================

@orders_bp.route("", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def create_order():
    user_id = get_jwt_identity()
    claims = get_jwt()
    device_id = claims.get("device_id", "K01")
    data = request.get_json() or {}

    idempotency_key = data.get("idempotency_key")
    if idempotency_key:
        existing = Order.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return api_response({"id": existing.id, "order_no": existing.order_no}, "Order sudah diproses (idempotent)")

    source = data.get("source", SOURCE_POS)
    order_type = data.get("order_type", TYPE_DINE_IN)
    table_id = data.get("table_id")
    channel_id = data.get("channel_id")
    external_order_id = data.get("external_order_id")
    customer_name = data.get("customer_name")
    shift_id = data.get("shift_id")
    items_data = data.get("items", [])

    if not items_data:
        return error_response("Item pesanan tidak boleh kosong", 400)

    order_no = generate_order_number(device_id)

    # Calculate totals
    subtotal = Decimal("0.00")
    order_items = []
    for it in items_data:
        qty = Decimal(str(it.get("quantity", 1)))
        unit_price = Decimal(str(it.get("unit_price", 0)))
        item_discount = Decimal(str(it.get("discount", 0)))
        item_subtotal = (qty * unit_price) - item_discount
        subtotal += item_subtotal

        order_item = OrderItem(
            menu_id=it["menu_id"],
            variant_id=it.get("variant_id"),
            item_name=it["item_name"],
            quantity=qty,
            unit_price=unit_price,
            discount=item_discount,
            subtotal=item_subtotal,
            notes=it.get("notes")
        )

        for mod in it.get("modifiers", []):
            mod_price = Decimal(str(mod.get("price", 0)))
            subtotal += mod_price * qty
            order_item.modifiers.append(OrderItemModifier(
                modifier_id=mod["modifier_id"],
                modifier_name=mod["modifier_name"],
                price=mod_price
            ))

        order_items.append(order_item)

    transaction_discount = Decimal(str(data.get("discount", 0)))
    platform_commission = Decimal(str(data.get("platform_commission", 0)))
    total = subtotal - transaction_discount

    # POS orders are directly APPROVED
    initial_status = STATUS_APPROVED if source in [SOURCE_POS, SOURCE_ONLINE] else STATUS_PENDING_APPROVAL
    initial_payment_status = PAYMENT_PAID if data.get("is_paid") else PAYMENT_UNPAID

    order = Order(
        order_no=order_no,
        source=source,
        order_type=order_type,
        table_id=table_id,
        channel_id=channel_id,
        external_order_id=external_order_id,
        status=initial_status,
        payment_status=initial_payment_status,
        subtotal=subtotal,
        discount=transaction_discount,
        platform_commission=platform_commission,
        total=total,
        customer_name=customer_name,
        shift_id=shift_id,
        approved_by=user_id if initial_status == STATUS_APPROVED else None,
        approved_at=datetime.now(timezone.utc) if initial_status == STATUS_APPROVED else None,
        idempotency_key=idempotency_key,
        device_id=device_id,
        created_by=user_id
    )

    for oi in order_items:
        order.items.append(oi)

    db.session.add(order)
    db.session.flush()

    # Log status
    db.session.add(OrderStatusLog(
        order_id=order.id,
        to_status=initial_status,
        changed_by=user_id,
        notes="Pesanan dibuat"
    ))

    # If APPROVED immediately (POS), deduct stock based on recipe
    if initial_status == STATUS_APPROVED:
        deduct_stock_for_order(order)

    # Process payment if provided in payload
    payment_data = data.get("payment")
    if payment_data:
        amount = Decimal(str(payment_data.get("amount", total)))
        change = amount - total if amount > total else Decimal("0.00")
        payment = Payment(
            order_id=order.id,
            payment_method=payment_data.get("payment_method", "TUNAI"),
            amount=amount,
            change_amount=change,
            status=PAYMENT_PAID,
            provider=payment_data.get("provider"),
            provider_ref=payment_data.get("provider_ref"),
            paid_at=datetime.now(timezone.utc)
        )
        db.session.add(payment)
        order.payment_status = PAYMENT_PAID

    db.session.commit()

    # Emit socket event
    socketio.emit("order_created", {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "total": float(order.total)
    }, namespace="/ws")

    return api_response({
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "total": float(order.total)
    }, "Order berhasil dibuat", 201)


# ==================== UPDATE STATUS ====================

@orders_bp.route("/<order_id>/status", methods=["PATCH"])
@jwt_required()
@role_required(*ALL_ROLES)
def update_order_status(order_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    new_status = data.get("status")

    valid_statuses = [STATUS_PREPARING, STATUS_READY, STATUS_COMPLETED]
    if new_status not in valid_statuses:
        return error_response(f"Status tidak valid. Harus salah satu dari {valid_statuses}", 400)

    order = Order.query.get(order_id)
    if not order:
        return error_response("Order tidak ditemukan", 404)

    old_status = order.status
    order.status = new_status

    db.session.add(OrderStatusLog(
        order_id=order.id,
        from_status=old_status,
        to_status=new_status,
        changed_by=user_id,
        notes=data.get("notes")
    ))
    db.session.commit()

    socketio.emit("order_status_updated", {
        "order_id": order.id,
        "from_status": old_status,
        "to_status": new_status
    }, namespace="/ws")

    return api_response({"id": order.id, "status": order.status}, "Status pesanan diperbarui")


# ==================== PAYMENTS ====================

@orders_bp.route("/<order_id>/payments", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def add_payment(order_id):
    order = Order.query.get(order_id)
    if not order:
        return error_response("Order tidak ditemukan", 404)

    data = request.get_json() or {}
    payment_method = data.get("payment_method", "TUNAI").upper()
    amount = Decimal(str(data.get("amount", order.total)))
    change = amount - order.total if amount > order.total else Decimal("0.00")

    payment = Payment(
        order_id=order.id,
        payment_method=payment_method,
        amount=amount,
        change_amount=change,
        status=PAYMENT_PAID,
        paid_at=datetime.now(timezone.utc)
    )
    db.session.add(payment)
    order.payment_status = PAYMENT_PAID
    db.session.commit()

    return api_response({
        "id": payment.id,
        "amount": float(payment.amount),
        "change_amount": float(payment.change_amount),
        "status": payment.status
    }, "Pembayaran berhasil dicatat")


# ==================== VOID / REFUND ====================

@orders_bp.route("/<order_id>/void", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def void_order(order_id):
    """
    Void an order. Requires Admin PIN authorization.
    Reverts stock deductions and marks status CANCELLED.
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    admin_pin = str(data.get("admin_pin", "")).strip()
    reason = data.get("reason", "").strip()

    if not admin_pin or not reason:
        return error_response("PIN Admin dan alasan void wajib diisi", 400)

    # Verify admin PIN
    admins = User.query.filter(User.role.in_([ROLE_ADMIN, ROLE_SUPER_ADMIN]), User.is_active.is_(True)).all()
    valid_admin = None
    for adm in admins:
        if adm.pin_hash and verify_password(adm.pin_hash, admin_pin):
            valid_admin = adm
            break

    if not valid_admin:
        return error_response("PIN Admin tidak valid", 401)

    order = Order.query.get(order_id)
    if not order:
        return error_response("Order tidak ditemukan", 404)

    if order.status == STATUS_CANCELLED:
        return error_response("Order sudah dibatalkan sebelumnya", 400)

    old_status = order.status
    order.status = STATUS_CANCELLED
    if order.payment_status == PAYMENT_PAID:
        order.payment_status = PAYMENT_REFUNDED
        for p in order.payments:
            p.status = PAYMENT_REFUNDED

    # Revert stock movements
    return_stock_for_void(order)

    # Log status change and audit log
    db.session.add(OrderStatusLog(
        order_id=order.id,
        from_status=old_status,
        to_status=STATUS_CANCELLED,
        changed_by=valid_admin.id,
        notes=f"VOID oleh {valid_admin.name}: {reason}"
    ))

    db.session.add(AuditLog(
        user_id=valid_admin.id,
        action="VOID",
        entity="Order",
        entity_id=order.id,
        old_values=f"status={old_status}",
        new_values=f"status={STATUS_CANCELLED}, reason={reason}",
        ip_address=request.remote_addr
    ))

    db.session.commit()

    socketio.emit("order_voided", {"order_id": order.id, "order_no": order.order_no}, namespace="/ws")
    return api_response({"id": order.id, "status": order.status}, "Order berhasil di-void")


# ==================== QR APPROVAL (KASIR) ====================

@orders_bp.route("/pending-approval", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def list_pending_approval():
    """List pending cash QR orders for cashier inbox."""
    pending_orders = Order.query.filter_by(status=STATUS_PENDING_APPROVAL).order_by(Order.created_at.asc()).all()
    result = [{
        "id": o.id,
        "order_no": o.order_no,
        "order_type": o.order_type,
        "customer_name": o.customer_name,
        "table_number": o.table.table_number if o.table else None,
        "total": float(o.total),
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "items": [{
            "item_name": item.item_name,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "subtotal": float(item.subtotal),
            "notes": item.notes
        } for item in o.items]
    } for o in pending_orders]
    return api_response(result)


@orders_bp.route("/<order_id>/approve", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def approve_order(order_id):
    """
    Cashier approves QR cash order.
    Locks row to prevent race conditions across multiple devices.
    """
    user_id = get_jwt_identity()
    order = Order.query.filter_by(id=order_id).with_for_update().first()
    if not order:
        return error_response("Order tidak ditemukan", 404)

    if order.status != STATUS_PENDING_APPROVAL:
        return error_response(f"Order sudah dalam status {order.status}", 409)

    order.status = STATUS_APPROVED
    order.approved_by = user_id
    order.approved_at = datetime.now(timezone.utc)

    # Deduct stock upon approval
    deduct_stock_for_order(order)

    db.session.add(OrderStatusLog(
        order_id=order.id,
        from_status=STATUS_PENDING_APPROVAL,
        to_status=STATUS_APPROVED,
        changed_by=user_id,
        notes="Disetujui oleh kasir"
    ))
    db.session.commit()

    socketio.emit("order_approved", {
        "order_id": order.id,
        "order_no": order.order_no
    }, namespace="/ws")

    return api_response({"id": order.id, "status": order.status}, "Order disetujui")


@orders_bp.route("/<order_id>/reject", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def reject_order(order_id):
    """Cashier rejects QR cash order with required reason."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    reason = data.get("reason", "").strip()

    if not reason:
        return error_response("Alasan penolakan wajib diisi", 400)

    order = Order.query.filter_by(id=order_id).with_for_update().first()
    if not order:
        return error_response("Order tidak ditemukan", 404)

    if order.status != STATUS_PENDING_APPROVAL:
        return error_response(f"Order sudah dalam status {order.status}", 409)

    order.status = STATUS_REJECTED
    order.rejection_reason = reason

    db.session.add(OrderStatusLog(
        order_id=order.id,
        from_status=STATUS_PENDING_APPROVAL,
        to_status=STATUS_REJECTED,
        changed_by=user_id,
        notes=f"Ditolak kasir: {reason}"
    ))
    db.session.commit()

    socketio.emit("order_rejected", {
        "order_id": order.id,
        "reason": reason
    }, namespace="/ws")

    return api_response({"id": order.id, "status": order.status}, "Order ditolak")

