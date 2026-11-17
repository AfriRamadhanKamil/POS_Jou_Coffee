from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import (
    role_required, ALL_ROLES, ROLE_KASIR, ROLE_ADMIN, ROLE_SUPER_ADMIN
)
from app.finance.models import (
    ExpenseCategory, Expense, CashShift, CashMovement
)
from app.orders.models import Payment, Order

finance_bp = Blueprint("finance", __name__, url_prefix="/api/v1")


def _parse_amount(value, default=None):
    try:
        amount = Decimal(str(default if value is None else value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() else None


def _idempotency_key(data):
    key = data.get("idempotency_key")
    if not isinstance(key, str) or not key.strip() or len(key.strip()) > 64:
        return None
    return key.strip()


def _validate_shift_owner(shift, user_id, role):
    return role in {ROLE_ADMIN, ROLE_SUPER_ADMIN} or shift.user_id == user_id


def _shift_result(shift):
    return {
        "id": shift.id,
        "starting_cash": float(shift.starting_cash),
        "status": shift.status
    }


@finance_bp.route("/expense-categories", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def list_expense_categories():
    categories = ExpenseCategory.query_active().order_by(ExpenseCategory.name).all()
    return api_response([{
        "id": category.id,
        "name": category.name,
        "description": category.description
    } for category in categories])


@finance_bp.route("/expense-categories", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_expense_category():
    data = request.get_json() or {}
    name = data.get("name", "")
    if not isinstance(name, str):
        return error_response("Nama kategori tidak valid", 400)
    name = name.strip()
    if not name:
        return error_response("Nama kategori wajib diisi", 400)
    if ExpenseCategory.query_active().filter(db.func.lower(ExpenseCategory.name) == name.lower()).first():
        return error_response("Kategori pengeluaran sudah tersedia", 409)

    category = ExpenseCategory(name=name, description=data.get("description"))
    db.session.add(category)
    db.session.commit()
    return api_response({
        "id": category.id,
        "name": category.name,
        "description": category.description
    }, "Kategori pengeluaran dibuat", 201)


@finance_bp.route("/expense-categories/<category_id>", methods=["PATCH"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def update_expense_category(category_id):
    category = ExpenseCategory.query_active().filter_by(id=category_id).first()
    if not category:
        return error_response("Kategori pengeluaran tidak ditemukan", 404)

    data = request.get_json() or {}
    if "name" in data:
        name = data["name"]
        if not isinstance(name, str):
            return error_response("Nama kategori tidak valid", 400)
        name = name.strip()
        if not name:
            return error_response("Nama kategori wajib diisi", 400)
        duplicate = ExpenseCategory.query_active().filter(
            db.func.lower(ExpenseCategory.name) == name.lower(),
            ExpenseCategory.id != category.id
        ).first()
        if duplicate:
            return error_response("Kategori pengeluaran sudah tersedia", 409)
        category.name = name
    if "description" in data:
        category.description = data["description"]

    db.session.commit()
    return api_response({
        "id": category.id,
        "name": category.name,
        "description": category.description
    }, "Kategori pengeluaran diperbarui")


@finance_bp.route("/expense-categories/<category_id>", methods=["DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def delete_expense_category(category_id):
    category = ExpenseCategory.query_active().filter_by(id=category_id).first()
    if not category:
        return error_response("Kategori pengeluaran tidak ditemukan", 404)
    if Expense.query_active().filter_by(category_id=category.id).first():
        return error_response("Kategori masih digunakan oleh pengeluaran", 409)

    category.soft_delete()
    db.session.commit()
    return api_response(None, "Kategori pengeluaran dihapus")


# ==================== CASH SHIFTS ====================

@finance_bp.route("/shifts", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def list_shifts():
    query = CashShift.query
    if get_jwt().get("role") == ROLE_KASIR:
        query = query.filter_by(user_id=get_jwt_identity())
    shifts = query.order_by(CashShift.opened_at.desc()).limit(30).all()
    result = [{
        "id": s.id,
        "user_id": s.user_id,
        "user_name": s.user.name if s.user else None,
        "device_id": s.device_id,
        "opened_at": s.opened_at.isoformat() if s.opened_at else None,
        "closed_at": s.closed_at.isoformat() if s.closed_at else None,
        "starting_cash": float(s.starting_cash),
        "ending_cash_expected": float(s.ending_cash_expected),
        "ending_cash_actual": float(s.ending_cash_actual),
        "cash_difference": float(s.cash_difference),
        "status": s.status
    } for s in shifts]
    return api_response(result)


@finance_bp.route("/shifts/current", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def get_current_shift():
    """Get active open shift for current user/device."""
    user_id = get_jwt_identity()
    shift = CashShift.query.filter_by(
        user_id=user_id,
        status="OPEN"
    ).order_by(CashShift.opened_at.desc()).first()
    if not shift:
        return api_response(None, "Tidak ada shift yang sedang terbuka")

    # Calculate expected cash: starting_cash + cash_in - cash_out - cash_expenses + paid_cash_orders
    cash_in = sum(m.amount for m in shift.movements if m.type == "CASH_IN")
    cash_out = sum(m.amount for m in shift.movements if m.type == "CASH_OUT")
    cash_expenses = sum(e.amount for e in shift.expenses)

    # Cash orders in this shift
    cash_payments = db.session.query(
        db.func.sum(Payment.amount - Payment.change_amount)
    ).join(Order).filter(
        Order.shift_id == shift.id,
        Payment.payment_method == "TUNAI",
        Payment.status == "PAID"
    ).scalar() or Decimal("0.00")

    expected_cash = shift.starting_cash + cash_in + cash_payments - cash_out - cash_expenses

    return api_response({
        "id": shift.id,
        "opened_at": shift.opened_at.isoformat(),
        "starting_cash": float(shift.starting_cash),
        "expected_cash_drawer": float(expected_cash),
        "total_cash_sales": float(cash_payments),
        "total_expenses": float(cash_expenses),
        "status": shift.status
    })


@finance_bp.route("/shifts/open", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def open_shift():
    user_id = get_jwt_identity()
    claims = get_jwt()
    device_id = claims.get("device_id")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request shift harus berupa objek JSON", 400)
    idempotency_key = _idempotency_key(data)
    if not idempotency_key:
        return error_response("idempotency_key wajib diisi (maksimal 64 karakter)", 400)
    starting_cash = _parse_amount(data.get("starting_cash"), 0)
    if starting_cash is None or starting_cash < 0:
        return error_response("Modal awal harus berupa angka non-negatif", 400)

    prior = CashShift.query.filter_by(idempotency_key=idempotency_key).first()
    if prior:
        if prior.user_id != user_id or prior.starting_cash != starting_cash:
            return error_response("idempotency_key sudah digunakan untuk shift lain", 409)
        return api_response(_shift_result(prior), "Shift sudah dibuka (idempotent)")

    existing = CashShift.query.filter_by(user_id=user_id, status="OPEN").first()
    if existing:
        return error_response("Sudah ada shift yang masih berstatus OPEN. Tutup shift terlebih dahulu.", 400)

    shift = CashShift(
        user_id=user_id,
        device_id=device_id,
        opened_at=datetime.now(timezone.utc),
        starting_cash=starting_cash,
        ending_cash_expected=starting_cash,
        status="OPEN",
        idempotency_key=idempotency_key,
        created_by=user_id
    )
    db.session.add(shift)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        prior = CashShift.query.filter_by(idempotency_key=idempotency_key).first()
        if not prior:
            raise
        if prior.user_id != user_id or prior.starting_cash != starting_cash:
            return error_response("idempotency_key sudah digunakan untuk shift lain", 409)
        return api_response(_shift_result(prior), "Shift sudah dibuka (idempotent)")

    return api_response(_shift_result(shift), "Shift dibuka", 201)


@finance_bp.route("/shifts/<shift_id>/close", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def close_shift(shift_id):
    shift = db.session.get(CashShift, shift_id)
    if not shift:
        return error_response("Shift tidak ditemukan atau sudah ditutup", 400)

    user_id = get_jwt_identity()
    role = get_jwt().get("role")
    if not _validate_shift_owner(shift, user_id, role):
        return error_response("Shift hanya dapat ditutup oleh pemiliknya atau Admin", 403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request penutupan shift harus berupa objek JSON", 400)
    idempotency_key = _idempotency_key(data)
    if not idempotency_key:
        return error_response("idempotency_key wajib diisi (maksimal 64 karakter)", 400)
    prior_close = CashShift.query.filter_by(
        close_idempotency_key=idempotency_key
    ).first()
    if prior_close:
        if prior_close.id != shift.id:
            return error_response("idempotency_key sudah digunakan untuk penutupan lain", 409)
        return api_response({
            "id": shift.id,
            "ending_cash_expected": float(shift.ending_cash_expected),
            "ending_cash_actual": float(shift.ending_cash_actual),
            "cash_difference": float(shift.cash_difference)
        }, "Shift sudah ditutup (idempotent)")
    if shift.status != "OPEN":
        return error_response("Shift tidak ditemukan atau sudah ditutup", 400)

    ending_cash_actual = _parse_amount(data.get("ending_cash_actual"), 0)
    if ending_cash_actual is None or ending_cash_actual < 0:
        return error_response("Kas aktual harus berupa angka non-negatif", 400)

    # Calculate expected cash drawer
    cash_in = sum(m.amount for m in shift.movements if m.type == "CASH_IN")
    cash_out = sum(m.amount for m in shift.movements if m.type == "CASH_OUT")
    cash_expenses = sum(e.amount for e in shift.expenses)
    cash_payments = db.session.query(
        db.func.sum(Payment.amount - Payment.change_amount)
    ).join(Order).filter(
        Order.shift_id == shift.id,
        Payment.payment_method == "TUNAI",
        Payment.status == "PAID"
    ).scalar() or Decimal("0.00")

    expected_cash = shift.starting_cash + cash_in + cash_payments - cash_out - cash_expenses
    diff = ending_cash_actual - expected_cash

    shift.closed_at = datetime.now(timezone.utc)
    shift.ending_cash_expected = expected_cash
    shift.ending_cash_actual = ending_cash_actual
    shift.cash_difference = diff
    shift.status = "CLOSED"
    shift.close_idempotency_key = idempotency_key

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        prior_close = CashShift.query.filter_by(
            close_idempotency_key=idempotency_key
        ).first()
        if not prior_close:
            raise
        if prior_close.id != shift_id:
            return error_response("idempotency_key sudah digunakan untuk penutupan lain", 409)
        shift = prior_close

    return api_response({
        "id": shift.id,
        "ending_cash_expected": float(expected_cash),
        "ending_cash_actual": float(ending_cash_actual),
        "cash_difference": float(diff)
    }, "Shift berhasil ditutup")


# ==================== CASH MOVEMENTS ====================

@finance_bp.route("/cash-movements", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def create_cash_movement():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request pergerakan kas harus berupa objek JSON", 400)
    shift_id = data.get("shift_id")
    movement_type = data.get("type", "CASH_IN")
    if not isinstance(movement_type, str):
        return error_response("Jenis pergerakan kas tidak valid", 400)
    movement_type = movement_type.upper()
    if movement_type not in {"CASH_IN", "CASH_OUT"}:
        return error_response("Jenis pergerakan kas harus CASH_IN atau CASH_OUT", 400)
    amount = _parse_amount(data.get("amount"), 0)
    notes = data.get("notes")
    idempotency_key = _idempotency_key(data)

    if not idempotency_key:
        return error_response("idempotency_key wajib diisi (maksimal 64 karakter)", 400)
    if not isinstance(shift_id, str) or not shift_id or amount is None or amount <= 0:
        return error_response("Shift ID dan jumlah positif wajib diisi", 400)
    if notes is not None and not isinstance(notes, str):
        return error_response("Catatan kas tidak valid", 400)
    prior = CashMovement.query.filter_by(idempotency_key=idempotency_key).first()
    if prior:
        if (
            prior.shift_id != shift_id
            or prior.type != movement_type
            or prior.amount != amount
            or prior.notes != notes
        ):
            return error_response("idempotency_key sudah digunakan untuk pergerakan kas lain", 409)
        return api_response(
            {"id": prior.id, "amount": float(prior.amount)},
            "Pergerakan kas sudah dicatat (idempotent)"
        )

    shift = db.session.get(CashShift, shift_id)
    if not shift or shift.status != "OPEN":
        return error_response("Shift tidak ditemukan atau sudah ditutup", 404)
    if not _validate_shift_owner(shift, get_jwt_identity(), get_jwt().get("role")):
        return error_response("Pergerakan kas hanya dapat dicatat pada shift sendiri", 403)

    movement = CashMovement(
        shift_id=shift_id,
        type=movement_type,
        amount=amount,
        notes=notes,
        idempotency_key=idempotency_key,
        created_by=get_jwt_identity()
    )
    db.session.add(movement)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        prior = CashMovement.query.filter_by(idempotency_key=idempotency_key).first()
        if not prior:
            raise
        if (
            prior.shift_id != shift_id
            or prior.type != movement_type
            or prior.amount != amount
            or prior.notes != notes
        ):
            return error_response("idempotency_key sudah digunakan untuk pergerakan kas lain", 409)
        return api_response(
            {"id": prior.id, "amount": float(prior.amount)},
            "Pergerakan kas sudah dicatat (idempotent)"
        )
    return api_response({"id": movement.id, "amount": float(movement.amount)}, "Kas masuk/keluar dicatat", 201)


# ==================== EXPENSES ====================

@finance_bp.route("/expenses", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def list_expenses():
    expenses = Expense.query_active().order_by(Expense.expense_date.desc()).all()
    result = [{
        "id": e.id,
        "category_id": e.category_id,
        "category_name": e.category.name if e.category else None,
        "amount": float(e.amount),
        "notes": e.notes,
        "receipt_image_url": e.receipt_image_url,
        "expense_date": e.expense_date.isoformat() if e.expense_date else None,
        "shift_id": e.shift_id
    } for e in expenses]
    return api_response(result)


@finance_bp.route("/expenses", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def create_expense():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request pengeluaran harus berupa objek JSON", 400)
    category_id = data.get("category_id")
    amount = _parse_amount(data.get("amount"), 0)
    notes = data.get("notes")
    receipt_image_url = data.get("receipt_image_url")
    shift_id = data.get("shift_id")
    idempotency_key = _idempotency_key(data)

    if not idempotency_key:
        return error_response("idempotency_key wajib diisi (maksimal 64 karakter)", 400)
    if not isinstance(category_id, str) or not category_id or amount is None or amount <= 0:
        return error_response("Kategori dan nominal pengeluaran wajib diisi", 400)
    if notes is not None and not isinstance(notes, str):
        return error_response("Catatan pengeluaran tidak valid", 400)
    if (
        receipt_image_url is not None
        and (
            not isinstance(receipt_image_url, str)
            or len(receipt_image_url) > 255
        )
    ):
        return error_response("URL foto nota tidak valid", 400)

    prior = Expense.query.filter_by(idempotency_key=idempotency_key).first()
    if prior:
        if (
            prior.category_id != category_id
            or prior.amount != amount
            or prior.notes != notes
            or prior.receipt_image_url != receipt_image_url
            or prior.shift_id != shift_id
        ):
            return error_response("idempotency_key sudah digunakan untuk pengeluaran lain", 409)
        return api_response(
            {"id": prior.id, "amount": float(prior.amount)},
            "Pengeluaran sudah dicatat (idempotent)"
        )
    category = ExpenseCategory.query_active().filter_by(id=category_id).first()
    if not category:
        return error_response("Kategori pengeluaran tidak ditemukan", 404)
    if shift_id is not None:
        if not isinstance(shift_id, str) or not shift_id:
            return error_response("Shift pengeluaran tidak valid", 400)
        shift = db.session.get(CashShift, shift_id)
        if not shift or shift.status != "OPEN":
            return error_response("Shift tidak ditemukan atau sudah ditutup", 404)
        if not _validate_shift_owner(shift, get_jwt_identity(), get_jwt().get("role")):
            return error_response("Pengeluaran hanya dapat dicatat pada shift sendiri", 403)

    expense = Expense(
        category_id=category_id,
        amount=amount,
        notes=notes,
        receipt_image_url=receipt_image_url,
        shift_id=shift_id,
        expense_date=datetime.now(timezone.utc),
        idempotency_key=idempotency_key,
        created_by=get_jwt_identity()
    )
    db.session.add(expense)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        prior = Expense.query.filter_by(idempotency_key=idempotency_key).first()
        if not prior:
            raise
        if (
            prior.category_id != category_id
            or prior.amount != amount
            or prior.notes != notes
            or prior.receipt_image_url != receipt_image_url
            or prior.shift_id != shift_id
        ):
            return error_response("idempotency_key sudah digunakan untuk pengeluaran lain", 409)
        return api_response(
            {"id": prior.id, "amount": float(prior.amount)},
            "Pengeluaran sudah dicatat (idempotent)"
        )
    return api_response({"id": expense.id, "amount": float(expense.amount)}, "Pengeluaran dicatat", 201)


@finance_bp.route("/expenses/<expense_id>", methods=["PATCH"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def update_expense(expense_id):
    expense = Expense.query_active().filter_by(id=expense_id).first()
    if not expense:
        return error_response("Pengeluaran tidak ditemukan", 404)

    data = request.get_json() or {}
    if "amount" in data:
        try:
            amount = Decimal(str(data["amount"]))
        except (InvalidOperation, TypeError, ValueError):
            return error_response("Nominal pengeluaran tidak valid", 400)
        if not amount.is_finite() or amount <= Decimal("0"):
            return error_response("Nominal pengeluaran harus lebih besar dari 0", 400)
        expense.amount = amount
    if "notes" in data:
        expense.notes = data["notes"]
    if "category_id" in data:
        if not ExpenseCategory.query_active().filter_by(id=data["category_id"]).first():
            return error_response("Kategori pengeluaran tidak ditemukan", 404)
        expense.category_id = data["category_id"]

    db.session.commit()
    return api_response({"id": expense.id}, "Pengeluaran diperbarui")


@finance_bp.route("/expenses/<expense_id>", methods=["DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def delete_expense(expense_id):
    expense = Expense.query_active().filter_by(id=expense_id).first()
    if not expense:
        return error_response("Pengeluaran tidak ditemukan", 404)

    expense.soft_delete()
    db.session.commit()
    return api_response(None, "Pengeluaran dihapus")
