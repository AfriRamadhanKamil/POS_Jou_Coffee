from decimal import Decimal
from decimal import InvalidOperation
from datetime import datetime, timezone
from flask import Blueprint, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import IntegrityError
from itsdangerous import BadSignature, URLSafeTimedSerializer
from app.extensions import db, socketio
from app.common.response import api_response, error_response
from app.common.auth import role_required, verify_password, ALL_ROLES, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.auth.models import User, AuditLog
from app.catalog.models import Menu, MenuVariant, Modifier, SalesChannel, MenuChannelPrice
from app.orders.models import (
    Order, OrderItem, OrderItemModifier, Payment, OrderStatusLog, Table,
    STATUS_AWAITING_PAYMENT, STATUS_PENDING_APPROVAL, STATUS_APPROVED,
    STATUS_PREPARING, STATUS_READY, STATUS_COMPLETED, STATUS_REJECTED,
    STATUS_EXPIRED, STATUS_CANCELLED,
    PAYMENT_UNPAID, PAYMENT_PAID, PAYMENT_REFUNDED,
    SOURCE_POS, SOURCE_QR, SOURCE_ONLINE,
    TYPE_DINE_IN, TYPE_TAKE_AWAY, TYPE_DELIVERY
)
from app.inventory.services import (
    InsufficientStockError, deduct_stock_for_order, return_stock_for_void
)

orders_bp = Blueprint("orders", __name__, url_prefix="/api/v1/orders")


def _parse_decimal(value, default):
    try:
        result = Decimal(str(default if value is None else value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _order_response_data(order):
    return {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "total": float(order.total)
    }


def _idempotent_order_response(idempotency_key, error):
    db.session.rollback()
    existing = Order.query.filter_by(idempotency_key=idempotency_key).first()
    if not existing:
        raise error
    return api_response(
        _order_response_data(existing),
        "Order sudah diproses (idempotent)"
    )


def _serialize_order(order):
    result = _order_response_data(order)
    result.update({
        "source": order.source,
        "order_type": order.order_type,
        "payment_status": order.payment_status,
        "subtotal": float(order.subtotal),
        "discount": float(order.discount),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [{
            "id": item.id,
            "menu_id": item.menu_id,
            "variant_id": item.variant_id,
            "item_name": item.item_name,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "discount": float(item.discount),
            "subtotal": float(item.subtotal),
            "notes": item.notes,
            "modifiers": [{
                "modifier_id": modifier.modifier_id,
                "modifier_name": modifier.modifier_name,
                "price": float(modifier.price)
            } for modifier in item.modifiers]
        } for item in order.items],
        "payments": [{
            "id": payment.id,
            "payment_method": payment.payment_method,
            "amount": float(payment.amount),
            "change_amount": float(payment.change_amount),
            "status": payment.status,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None
        } for payment in order.payments]
    })
    return result


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
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request pesanan harus berupa objek JSON", 400)

    idempotency_key = data.get("idempotency_key")
    if (
        not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or len(idempotency_key.strip()) > 64
    ):
        return error_response("idempotency_key wajib diisi (maksimal 64 karakter)", 400)
    idempotency_key = idempotency_key.strip()
    existing = Order.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return api_response(
            _order_response_data(existing),
            "Order sudah diproses (idempotent)"
        )

    source = data.get("source", SOURCE_POS)
    order_type = data.get("order_type", TYPE_DINE_IN)
    if not isinstance(source, str) or source not in {SOURCE_POS, SOURCE_QR, SOURCE_ONLINE}:
        return error_response("Source pesanan tidak valid", 400)
    if not isinstance(order_type, str) or order_type not in {
        TYPE_DINE_IN, TYPE_TAKE_AWAY, TYPE_DELIVERY
    }:
        return error_response("Tipe pesanan tidak valid", 400)
    channel = None
    channel_id = data.get("channel_id")
    external_order_id = data.get("external_order_id")
    if order_type == TYPE_DELIVERY:
        if (
            not isinstance(channel_id, str)
            or not channel_id.strip()
            or not isinstance(external_order_id, str)
            or not data["external_order_id"].strip()
            or len(external_order_id.strip()) > 100
        ):
            return error_response(
                "Pesanan delivery membutuhkan channel_id dan external_order_id",
                400
            )
        channel_id = channel_id.strip()
        external_order_id = external_order_id.strip()
        channel = SalesChannel.query_active().filter_by(id=channel_id).first()
        if not channel:
            return error_response("Channel penjualan tidak ditemukan", 404)
        existing_external = Order.query.filter_by(
            channel_id=channel_id,
            external_order_id=external_order_id
        ).first()
        if existing_external:
            return api_response(
                _order_response_data(existing_external),
                "Order platform sudah diproses (idempotent)"
            )
        source = SOURCE_ONLINE
    table_id = data.get("table_id")
    customer_name = data.get("customer_name")
    shift_id = data.get("shift_id")
    items_data = data.get("items", [])

    if not isinstance(items_data, list) or not items_data:
        return error_response("Item pesanan tidak boleh kosong", 400)

    order_no = generate_order_number(device_id)

    # Calculate totals
    subtotal = Decimal("0.00")
    gross_subtotal = Decimal("0.00")
    item_discounts = Decimal("0.00")
    order_items = []
    for index, it in enumerate(items_data):
        if not isinstance(it, dict):
            return error_response(f"Item pesanan {index} tidak valid", 400)
        if not isinstance(it.get("menu_id"), str) or not it["menu_id"].strip():
            return error_response(f"Item pesanan {index} membutuhkan menu_id", 400)
        if not isinstance(it.get("item_name"), str) or not it["item_name"].strip():
            return error_response(f"Item pesanan {index} membutuhkan item_name", 400)
        if it.get("variant_id") is not None and not isinstance(it["variant_id"], str):
            return error_response(f"variant_id item {index} tidak valid", 400)
        if it.get("notes") is not None and not isinstance(it["notes"], str):
            return error_response(f"Catatan item {index} tidak valid", 400)

        menu = Menu.query_active().filter_by(id=it["menu_id"].strip()).first()
        if not menu or not menu.is_active or not menu.is_available:
            return error_response(f"Menu pada item {index} tidak tersedia", 404)

        qty = _parse_decimal(it.get("quantity"), 1)
        unit_price = _parse_decimal(it.get("unit_price"), 0)
        item_discount = _parse_decimal(it.get("discount"), 0)
        if (
            qty is None or qty <= 0
            or unit_price is None or unit_price < 0
            or item_discount is None or item_discount < 0
        ):
            return error_response(f"Jumlah, harga, atau diskon item {index} tidak valid", 400)
        variant = None
        variant_id = it.get("variant_id")
        if variant_id is not None:
            if not isinstance(variant_id, str):
                return error_response(f"variant_id item {index} tidak valid", 400)
            variant = MenuVariant.query_active().filter_by(
                id=variant_id,
                menu_id=menu.id
            ).first()
            if not variant or not variant.is_active:
                return error_response(f"Varian pada item {index} tidak tersedia", 404)
        if channel:
            channel_price = MenuChannelPrice.query_active().filter_by(
                menu_id=menu.id,
                channel_id=channel.id
            ).first()
            if not channel_price:
                return error_response(
                    f"Harga channel untuk menu item {index} belum diatur",
                    400
                )
            unit_price = Decimal(channel_price.price)
            if variant:
                unit_price += Decimal(variant.price_adjustment)
        if item_discount > qty * unit_price:
            return error_response(f"Diskon item {index} melebihi subtotal item", 400)

        modifier_data = it.get("modifiers", [])
        if not isinstance(modifier_data, list):
            return error_response(f"Modifier item {index} tidak valid", 400)
        modifier_total = Decimal("0.00")
        modifiers = []
        for modifier_index, mod in enumerate(modifier_data):
            if (
                not isinstance(mod, dict)
                or not isinstance(mod.get("modifier_id"), str)
                or not mod["modifier_id"].strip()
                or not isinstance(mod.get("modifier_name"), str)
                or not mod["modifier_name"].strip()
            ):
                return error_response(
                    f"Modifier {modifier_index} pada item {index} tidak valid",
                    400
                )
            modifier = Modifier.query_active().filter_by(
                id=mod["modifier_id"].strip()
            ).first()
            if not modifier or not modifier.is_active:
                return error_response(
                    f"Modifier {modifier_index} pada item {index} tidak tersedia",
                    404
                )
            mod_price = Decimal(modifier.price)
            modifier_total += mod_price * qty
            modifiers.append((modifier, mod_price))

        item_subtotal = (qty * unit_price) - item_discount + modifier_total
        gross_subtotal += qty * unit_price + modifier_total
        item_discounts += item_discount
        subtotal += item_subtotal

        order_item = OrderItem(
            menu_id=it["menu_id"].strip(),
            variant_id=variant.id if variant else None,
            item_name=(
                f"{menu.name} - {variant.name}"
                if variant else menu.name
            ),
            quantity=qty,
            unit_price=unit_price,
            discount=item_discount,
            subtotal=item_subtotal,
            notes=it.get("notes")
        )

        for modifier, mod_price in modifiers:
            order_item.modifiers.append(OrderItemModifier(
                modifier_id=modifier.id,
                modifier_name=modifier.name,
                price=mod_price
            ))

        order_items.append(order_item)

    transaction_discount = _parse_decimal(data.get("discount"), 0)
    platform_commission = _parse_decimal(data.get("platform_commission"), 0)
    if (
        transaction_discount is None or transaction_discount < 0
        or platform_commission is None or platform_commission < 0
    ):
        return error_response("Diskon atau komisi pesanan tidak valid", 400)
    if transaction_discount > subtotal:
        return error_response("Diskon pesanan melebihi subtotal", 400)
    total_discount = item_discounts + transaction_discount
    total = gross_subtotal - total_discount
    if channel:
        platform_commission = (
            total * Decimal(channel.commission_percent) / Decimal("100")
        ).quantize(Decimal("0.01"))
    max_discount_percent = _parse_decimal(
        current_app.config.get("MAX_ORDER_DISCOUNT_PERCENT"),
        10
    )
    if max_discount_percent is None or not Decimal("0") <= max_discount_percent <= Decimal("100"):
        raise ValueError("MAX_ORDER_DISCOUNT_PERCENT harus antara 0 dan 100")
    discount_approved_by = None
    if total_discount > gross_subtotal * max_discount_percent / Decimal("100"):
        approval_token = data.get("discount_approval_token")
        if not isinstance(approval_token, str) or not approval_token:
            return error_response(
                "Diskon di atas batas memerlukan persetujuan PIN Admin",
                403
            )
        serializer = URLSafeTimedSerializer(
            current_app.config["SECRET_KEY"],
            salt="jou-coffee-admin-approval"
        )
        try:
            approval = serializer.loads(approval_token, max_age=300)
        except BadSignature:
            return error_response("Token persetujuan diskon tidak valid atau kedaluwarsa", 403)
        if (
            not isinstance(approval, dict)
            or approval.get("purpose") != "order_discount"
            or approval.get("user_id") != user_id
        ):
            return error_response("Token persetujuan diskon tidak berlaku untuk pengguna ini", 403)
        approver = db.session.get(User, approval.get("approved_by"))
        if (
            not approver
            or not approver.is_active
            or approver.deleted_at is not None
            or approver.role not in {ROLE_ADMIN, ROLE_SUPER_ADMIN}
        ):
            return error_response("Admin yang menyetujui sudah tidak aktif", 403)
        discount_approved_by = approver.id
    payment_data = data.get("payment")
    if payment_data is None and channel:
        payment_data = {"payment_method": "PLATFORM", "amount": total}
    payment_amount = None
    payment_method = None
    if payment_data is not None:
        if not isinstance(payment_data, dict):
            return error_response("Data pembayaran tidak valid", 400)
        payment_amount = _parse_decimal(payment_data.get("amount"), total)
        payment_method = str(payment_data.get("payment_method", "TUNAI")).upper()
        payment_method = {
            "CASH": "TUNAI",
            "QRIS_STATIC": "QRIS_STATIS"
        }.get(payment_method, payment_method)
        if payment_amount is None or payment_amount < total:
            return error_response("Nominal pembayaran tidak mencukupi atau tidak valid", 400)
        if payment_method not in {
            "TUNAI", "QRIS_STATIS", "QRIS_DINAMIS", "PLATFORM"
        }:
            return error_response("Metode pembayaran tidak valid", 400)

    # POS orders are directly APPROVED
    initial_status = STATUS_APPROVED if source in [SOURCE_POS, SOURCE_ONLINE] else STATUS_PENDING_APPROVAL
    initial_payment_status = PAYMENT_UNPAID

    order = Order(
        order_no=order_no,
        source=source,
        order_type=order_type,
        table_id=table_id,
        channel_id=channel_id,
        external_order_id=external_order_id,
        status=initial_status,
        payment_status=initial_payment_status,
        subtotal=gross_subtotal,
        discount=total_discount,
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
    try:
        db.session.flush()
    except IntegrityError as error:
        return _idempotent_order_response(idempotency_key, error)

    # Log status
    db.session.add(OrderStatusLog(
        order_id=order.id,
        to_status=initial_status,
        changed_by=user_id,
        notes="Pesanan dibuat"
    ))

    # If APPROVED immediately (POS), deduct stock based on recipe
    if initial_status == STATUS_APPROVED:
        try:
            deduct_stock_for_order(order)
        except InsufficientStockError as error:
            db.session.rollback()
            return error_response(str(error), 409)

    # Process payment if provided in payload
    if payment_data is not None:
        change = payment_amount - total if payment_amount > total else Decimal("0.00")
        payment = Payment(
            order_id=order.id,
            payment_method=payment_method,
            amount=payment_amount,
            change_amount=change,
            status=PAYMENT_PAID,
            provider=payment_data.get("provider"),
            provider_ref=payment_data.get("provider_ref"),
            paid_at=datetime.now(timezone.utc)
        )
        db.session.add(payment)
        order.payment_status = PAYMENT_PAID
        if payment_method == "QRIS_STATIS":
            db.session.add(AuditLog(
                user_id=user_id,
                action="QRIS_STATIC_PAYMENT",
                entity="Order",
                entity_id=order.id,
                new_values=f"payment_method={payment_method}, amount={payment_amount}",
                ip_address=request.remote_addr
            ))
    if discount_approved_by:
        db.session.add(AuditLog(
            user_id=discount_approved_by,
            action="ORDER_DISCOUNT_APPROVED",
            entity="Order",
            entity_id=order.id,
            new_values=f"discount={transaction_discount}",
            ip_address=request.remote_addr
        ))

    try:
        db.session.commit()
    except IntegrityError as error:
        return _idempotent_order_response(idempotency_key, error)

    # Emit socket event
    socketio.emit("order_created", {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "total": float(order.total)
    }, namespace="/ws")

    return api_response(_order_response_data(order), "Order berhasil dibuat", 201)


@orders_bp.route("", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def list_orders():
    query = Order.query
    status = request.args.get("status")
    cashier_id = request.args.get("cashier_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if status:
        query = query.filter_by(status=status)
    if cashier_id:
        query = query.filter_by(created_by=cashier_id)
    for parameter, value, operator in (
        ("start_date", start_date, "start"),
        ("end_date", end_date, "end")
    ):
        if not value:
            continue
        try:
            bound = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return error_response(f"{parameter} harus berupa waktu ISO-8601", 400)
        if bound.tzinfo is None:
            bound = bound.replace(tzinfo=timezone.utc)
        if operator == "start":
            query = query.filter(Order.created_at >= bound)
        else:
            query = query.filter(Order.created_at <= bound)

    try:
        limit = int(request.args.get("limit", 100))
    except ValueError:
        return error_response("limit harus berupa bilangan bulat", 400)
    if limit < 1 or limit > 500:
        return error_response("limit harus antara 1 dan 500", 400)

    orders = query.order_by(Order.created_at.desc()).limit(limit).all()
    return api_response([_serialize_order(order) for order in orders])


@orders_bp.route("/<order_id>", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def get_order(order_id):
    order = Order.query.filter_by(id=order_id).first()
    if not order:
        return error_response("Order tidak ditemukan", 404)
    return api_response(_serialize_order(order))


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

    order = db.session.get(Order, order_id)
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
    order = db.session.get(Order, order_id)
    if not order:
        return error_response("Order tidak ditemukan", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request pembayaran harus berupa objek JSON", 400)
    idempotency_key = data.get("idempotency_key")
    if (
        not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or len(idempotency_key.strip()) > 64
    ):
        return error_response("idempotency_key wajib diisi (maksimal 64 karakter)", 400)
    idempotency_key = idempotency_key.strip()

    payment_method = data.get("payment_method", "TUNAI")
    if not isinstance(payment_method, str):
        return error_response("Metode pembayaran tidak valid", 400)
    payment_method = payment_method.upper()
    payment_method = {
        "CASH": "TUNAI",
        "QRIS_STATIC": "QRIS_STATIS"
    }.get(payment_method, payment_method)
    if payment_method not in {
        "TUNAI", "QRIS_STATIS", "QRIS_DINAMIS", "PLATFORM"
    }:
        return error_response("Metode pembayaran tidak valid", 400)

    amount = _parse_decimal(data.get("amount"), order.total)
    if amount is None or amount < order.total:
        return error_response("Nominal pembayaran tidak mencukupi atau tidak valid", 400)

    existing = Payment.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        if (
            existing.order_id != order.id
            or existing.payment_method != payment_method
            or existing.amount != amount
        ):
            return error_response("idempotency_key sudah digunakan untuk pembayaran lain", 409)
        return api_response({
            "id": existing.id,
            "amount": float(existing.amount),
            "change_amount": float(existing.change_amount),
            "status": existing.status
        }, "Pembayaran sudah dicatat (idempotent)")
    if order.payment_status == PAYMENT_PAID:
        return error_response("Pesanan sudah dibayar", 409)

    change = amount - order.total if amount > order.total else Decimal("0.00")

    payment = Payment(
        order_id=order.id,
        payment_method=payment_method,
        amount=amount,
        change_amount=change,
        status=PAYMENT_PAID,
        idempotency_key=idempotency_key,
        paid_at=datetime.now(timezone.utc)
    )
    db.session.add(payment)
    order.payment_status = PAYMENT_PAID
    if payment_method == "QRIS_STATIS":
        db.session.add(AuditLog(
            user_id=get_jwt_identity(),
            action="QRIS_STATIC_PAYMENT",
            entity="Order",
            entity_id=order.id,
            new_values=f"payment_method={payment_method}, amount={amount}",
            ip_address=request.remote_addr
        ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = Payment.query.filter_by(idempotency_key=idempotency_key).first()
        if not existing:
            raise
        if (
            existing.order_id != order.id
            or existing.payment_method != payment_method
            or existing.amount != amount
        ):
            return error_response("idempotency_key sudah digunakan untuk pembayaran lain", 409)
        return api_response({
            "id": existing.id,
            "amount": float(existing.amount),
            "change_amount": float(existing.change_amount),
            "status": existing.status
        }, "Pembayaran sudah dicatat (idempotent)")

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

    order = db.session.get(Order, order_id)
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
    try:
        deduct_stock_for_order(order)
    except InsufficientStockError as error:
        db.session.rollback()
        return error_response(str(error), 409)

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

