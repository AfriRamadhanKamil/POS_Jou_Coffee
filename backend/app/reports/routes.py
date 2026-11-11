from datetime import datetime, timezone
from decimal import Decimal
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func, extract
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import role_required, ALL_ROLES, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.orders.models import (
    Order, OrderItem, Payment,
    STATUS_APPROVED, STATUS_PREPARING, STATUS_READY, STATUS_COMPLETED
)
from app.inventory.models import Recipe, RecipeItem, Ingredient
from app.finance.models import Expense, CashMovement

reports_bp = Blueprint("reports", __name__, url_prefix="/api/v1/reports")

VALID_REPORT_STATUSES = [STATUS_APPROVED, STATUS_PREPARING, STATUS_READY, STATUS_COMPLETED]


@reports_bp.route("/sales", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def get_sales_report():
    """
    Sales report with filters:
    - start_date (YYYY-MM-DD)
    - end_date (YYYY-MM-DD)
    - order_type (DINE_IN, TAKE_AWAY, DELIVERY)
    - channel_id
    - payment_method
    """
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    order_type = request.args.get("order_type")
    channel_id = request.args.get("channel_id")

    query = Order.query.filter(Order.status.in_(VALID_REPORT_STATUSES))

    if start_date_str:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        query = query.filter(Order.created_at >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        query = query.filter(Order.created_at <= end_date)
    if order_type:
        query = query.filter_by(order_type=order_type)
    if channel_id:
        query = query.filter_by(channel_id=channel_id)

    orders = query.order_by(Order.created_at.desc()).all()

    total_gross = sum(o.subtotal for o in orders)
    total_discount = sum(o.discount for o in orders)
    total_net = sum(o.total for o in orders)
    total_commission = sum(o.platform_commission for o in orders)

    orders_list = [{
        "id": o.id,
        "order_no": o.order_no,
        "source": o.source,
        "order_type": o.order_type,
        "customer_name": o.customer_name,
        "subtotal": float(o.subtotal),
        "discount": float(o.discount),
        "total": float(o.total),
        "status": o.status,
        "payment_status": o.payment_status,
        "created_at": o.created_at.isoformat() if o.created_at else None
    } for o in orders]

    return api_response({
        "summary": {
            "order_count": len(orders),
            "total_gross": float(total_gross),
            "total_discount": float(total_discount),
            "total_net": float(total_net),
            "total_platform_commission": float(total_commission)
        },
        "orders": orders_list
    })


@reports_bp.route("/cash-summary", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def get_cash_summary():
    """Summary of cash vs non-cash payments."""
    payments = Payment.query.filter_by(status="PAID").all()

    cash_total = Decimal("0.00")
    qris_total = Decimal("0.00")
    platform_total = Decimal("0.00")

    for p in payments:
        if p.payment_method == "TUNAI":
            cash_total += p.amount - p.change_amount
        elif "QRIS" in p.payment_method:
            qris_total += p.amount
        elif p.payment_method == "PLATFORM":
            platform_total += p.amount

    return api_response({
        "cash_drawer_total": float(cash_total),
        "qris_total": float(qris_total),
        "platform_total": float(platform_total),
        "grand_total": float(cash_total + qris_total + platform_total)
    })


@reports_bp.route("/charts", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def get_charts():
    """Data for sales per day, hourly distribution, top selling items, and channels."""
    # Top 5 items
    top_items = db.session.query(
        OrderItem.item_name,
        func.sum(OrderItem.quantity).label("total_qty"),
        func.sum(OrderItem.subtotal).label("total_sales")
    ).join(Order).filter(
        Order.status.in_(VALID_REPORT_STATUSES)
    ).group_by(OrderItem.item_name).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()

    top_items_data = [{
        "name": row[0],
        "quantity": float(row[1]),
        "sales": float(row[2])
    } for row in top_items]

    # Breakdown by order type
    by_type = db.session.query(
        Order.order_type,
        func.count(Order.id),
        func.sum(Order.total)
    ).filter(
        Order.status.in_(VALID_REPORT_STATUSES)
    ).group_by(Order.order_type).all()

    by_type_data = [{
        "order_type": row[0],
        "count": row[1],
        "total": float(row[2] or 0)
    } for row in by_type]

    return api_response({
        "top_selling_menus": top_items_data,
        "sales_by_order_type": by_type_data
    })


@reports_bp.route("/profit", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def get_profit_report():
    """
    Gross profit calculation = Total Net Sales - Total COGS (HPP from recipes).
    Restricted to Admin/Owner and Super Admin. Kasir cannot access this.
    """
    orders = Order.query.filter(Order.status.in_(VALID_REPORT_STATUSES)).all()
    total_sales = sum(o.total for o in orders)

    total_cogs = Decimal("0.00")
    for order in orders:
        for item in order.items:
            recipe = Recipe.query_active().filter_by(menu_id=item.menu_id, variant_id=item.variant_id).first()
            if not recipe and item.variant_id:
                recipe = Recipe.query_active().filter_by(menu_id=item.menu_id, variant_id=None).first()

            if recipe:
                for r_item in recipe.items:
                    ing = r_item.ingredient
                    if ing:
                        item_cogs = r_item.quantity * ing.last_purchase_price * item.quantity
                        total_cogs += item_cogs

    gross_profit = total_sales - total_cogs
    margin_percent = (gross_profit / total_sales * 100) if total_sales > Decimal("0") else Decimal("0")

    return api_response({
        "total_revenue": float(total_sales),
        "total_cogs": float(total_cogs),
        "gross_profit": float(gross_profit),
        "margin_percentage": float(margin_percent)
    })
