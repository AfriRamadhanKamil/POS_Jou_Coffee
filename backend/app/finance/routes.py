from decimal import Decimal
from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import role_required, ALL_ROLES, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.finance.models import (
    ExpenseCategory, Expense, CashShift, CashMovement
)
from app.orders.models import Payment, Order

finance_bp = Blueprint("finance", __name__, url_prefix="/api/v1")


# ==================== CASH SHIFTS ====================

@finance_bp.route("/shifts", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def list_shifts():
    shifts = CashShift.query.order_by(CashShift.opened_at.desc()).limit(30).all()
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
    shift = CashShift.query.filter_by(status="OPEN").order_by(CashShift.opened_at.desc()).first()
    if not shift:
        return api_response(None, "Tidak ada shift yang sedang terbuka")

    # Calculate expected cash: starting_cash + cash_in - cash_out - cash_expenses + paid_cash_orders
    cash_in = sum(m.amount for m in shift.movements if m.type == "CASH_IN")
    cash_out = sum(m.amount for m in shift.movements if m.type == "CASH_OUT")
    cash_expenses = sum(e.amount for e in shift.expenses)

    # Cash orders in this shift
    cash_payments = db.session.query(db.func.sum(Payment.amount)).join(Order).filter(
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

    # Check if there is already an open shift
    existing = CashShift.query.filter_by(status="OPEN").first()
    if existing:
        return error_response("Sudah ada shift yang masih berstatus OPEN. Tutup shift terlebih dahulu.", 400)

    data = request.get_json() or {}
    starting_cash = Decimal(str(data.get("starting_cash", 0.0)))

    shift = CashShift(
        user_id=user_id,
        device_id=device_id,
        opened_at=datetime.now(timezone.utc),
        starting_cash=starting_cash,
        ending_cash_expected=starting_cash,
        status="OPEN"
    )
    db.session.add(shift)
    db.session.commit()

    return api_response({"id": shift.id, "starting_cash": float(shift.starting_cash)}, "Shift dibuka", 201)


@finance_bp.route("/shifts/<shift_id>/close", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def close_shift(shift_id):
    shift = CashShift.query.get(shift_id)
    if not shift or shift.status != "OPEN":
        return error_response("Shift tidak ditemukan atau sudah ditutup", 400)

    data = request.get_json() or {}
    ending_cash_actual = Decimal(str(data.get("ending_cash_actual", 0.0)))

    # Calculate expected cash drawer
    cash_in = sum(m.amount for m in shift.movements if m.type == "CASH_IN")
    cash_out = sum(m.amount for m in shift.movements if m.type == "CASH_OUT")
    cash_expenses = sum(e.amount for e in shift.expenses)
    cash_payments = db.session.query(db.func.sum(Payment.amount)).join(Order).filter(
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

    db.session.commit()

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
    data = request.get_json() or {}
    shift_id = data.get("shift_id")
    movement_type = data.get("type", "CASH_IN").upper()
    amount = Decimal(str(data.get("amount", 0.0)))
    notes = data.get("notes")

    if not shift_id or amount <= Decimal("0"):
        return error_response("Shift ID dan jumlah wajib diisi", 400)

    movement = CashMovement(
        shift_id=shift_id,
        type=movement_type,
        amount=amount,
        notes=notes
    )
    db.session.add(movement)
    db.session.commit()
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
    data = request.get_json() or {}
    category_id = data.get("category_id")
    amount = Decimal(str(data.get("amount", 0.0)))
    notes = data.get("notes")
    receipt_image_url = data.get("receipt_image_url")
    shift_id = data.get("shift_id")

    if not category_id or amount <= Decimal("0"):
        return error_response("Kategori dan nominal pengeluaran wajib diisi", 400)

    expense = Expense(
        category_id=category_id,
        amount=amount,
        notes=notes,
        receipt_image_url=receipt_image_url,
        shift_id=shift_id,
        expense_date=datetime.now(timezone.utc)
    )
    db.session.add(expense)
    db.session.commit()
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
        expense.amount = Decimal(str(data["amount"]))
    if "notes" in data:
        expense.notes = data["notes"]
    if "category_id" in data:
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

