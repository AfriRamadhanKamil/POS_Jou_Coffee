from decimal import Decimal
from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import role_required, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.inventory.models import (
    Unit, Ingredient, Recipe, RecipeItem, StockMovement,
    StockBalance, Purchase, PurchaseItem, StockOpname, StockOpnameItem
)
from app.inventory.services import (
    record_stock_movement, calculate_recipe_cogs
)

inventory_bp = Blueprint("inventory", __name__, url_prefix="/api/v1")


# ==================== INGREDIENTS ====================

@inventory_bp.route("/ingredients", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def list_ingredients():
    ingredients = Ingredient.query_active().all()
    result = [{
        "id": ing.id,
        "name": ing.name,
        "unit_id": ing.unit_id,
        "unit_symbol": ing.unit.symbol if ing.unit else None,
        "min_stock": float(ing.min_stock),
        "current_stock": float(ing.balance.current_stock) if ing.balance else 0.0,
        "last_purchase_price": float(ing.last_purchase_price),
        "is_low_stock": (ing.balance.current_stock <= ing.min_stock) if ing.balance else True
    } for ing in ingredients]
    return api_response(result)


@inventory_bp.route("/ingredients", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_ingredient():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    unit_id = data.get("unit_id")
    min_stock = Decimal(str(data.get("min_stock", 0.0)))
    last_price = Decimal(str(data.get("last_purchase_price", 0.0)))

    if not name or not unit_id:
        return error_response("Nama dan unit wajib diisi", 400)

    ingredient = Ingredient(
        name=name,
        unit_id=unit_id,
        min_stock=min_stock,
        last_purchase_price=last_price,
        is_active=True
    )
    db.session.add(ingredient)
    db.session.flush()

    # Initial balance entry
    balance = StockBalance(ingredient_id=ingredient.id, current_stock=Decimal("0.0000"))
    db.session.add(balance)

    db.session.commit()
    return api_response({"id": ingredient.id, "name": ingredient.name}, "Bahan baku dibuat", 201)


# ==================== RECIPES (BOM) ====================

@inventory_bp.route("/recipes", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def list_recipes():
    recipes = Recipe.query_active().all()
    result = [{
        "id": r.id,
        "menu_id": r.menu_id,
        "menu_name": r.menu.name if r.menu else None,
        "variant_id": r.variant_id,
        "variant_name": r.variant.name if r.variant else None,
        "cogs": float(calculate_recipe_cogs(r)),
        "items": [{
            "ingredient_id": item.ingredient_id,
            "ingredient_name": item.ingredient.name if item.ingredient else None,
            "quantity": float(item.quantity),
            "unit": item.ingredient.unit.symbol if (item.ingredient and item.ingredient.unit) else None
        } for item in r.items]
    } for r in recipes]
    return api_response(result)


@inventory_bp.route("/recipes", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_or_update_recipe():
    data = request.get_json() or {}
    menu_id = data.get("menu_id")
    variant_id = data.get("variant_id")
    items = data.get("items", [])

    if not menu_id or not items:
        return error_response("Menu dan daftar bahan resep wajib diisi", 400)

    # Check if recipe already exists for this menu + variant
    recipe = Recipe.query_active().filter_by(menu_id=menu_id, variant_id=variant_id).first()
    if not recipe:
        recipe = Recipe(menu_id=menu_id, variant_id=variant_id, notes=data.get("notes"))
        db.session.add(recipe)
        db.session.flush()
    else:
        # Clear existing items
        RecipeItem.query.filter_by(recipe_id=recipe.id).delete()

    for item in items:
        r_item = RecipeItem(
            recipe_id=recipe.id,
            ingredient_id=item["ingredient_id"],
            quantity=Decimal(str(item["quantity"]))
        )
        db.session.add(r_item)

    db.session.commit()
    return api_response({"id": recipe.id, "cogs": float(calculate_recipe_cogs(recipe))}, "Resep disimpan", 200)


# ==================== STOCK MOVEMENTS (ADJUSTMENT / WASTE) ====================

@inventory_bp.route("/stock/movements", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_stock_movement():
    data = request.get_json() or {}
    ingredient_id = data.get("ingredient_id")
    movement_type = data.get("type", "ADJUSTMENT").upper()  # ADJUSTMENT, WASTE
    quantity = Decimal(str(data.get("quantity", 0.0)))
    notes = data.get("notes")

    if not ingredient_id or quantity == Decimal("0"):
        return error_response("Ingredient dan jumlah tidak boleh 0", 400)

    movement = record_stock_movement(
        ingredient_id=ingredient_id,
        movement_type=movement_type,
        quantity=quantity,
        reference_type="MANUAL",
        notes=notes
    )
    db.session.commit()
    return api_response({
        "id": movement.id,
        "balance_after": float(movement.balance_after)
    }, "Pergerakan stok dicatat")


# ==================== STOCK OPNAME ====================

@inventory_bp.route("/stock/opname", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def record_opname():
    data = request.get_json() or {}
    items = data.get("items", [])
    notes = data.get("notes")

    if not items:
        return error_response("Item opname wajib diisi", 400)

    opname_no = f"OPN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    opname = StockOpname(opname_no=opname_no, notes=notes)
    db.session.add(opname)
    db.session.flush()

    for item in items:
        ing_id = item["ingredient_id"]
        actual_qty = Decimal(str(item["actual_stock"]))
        balance = StockBalance.query.filter_by(ingredient_id=ing_id).first()
        system_qty = balance.current_stock if balance else Decimal("0.0000")
        diff = actual_qty - system_qty

        op_item = StockOpnameItem(
            opname_id=opname.id,
            ingredient_id=ing_id,
            system_stock=system_qty,
            actual_stock=actual_qty,
            difference=diff
        )
        db.session.add(op_item)

        # Record adjustment movement for the difference
        if diff != Decimal("0"):
            record_stock_movement(
                ingredient_id=ing_id,
                movement_type="OPNAME",
                quantity=diff,
                reference_type="OPNAME",
                reference_id=opname.id,
                notes=f"Penyesuaian Opname #{opname.opname_no}"
            )

    db.session.commit()
    return api_response({"id": opname.id, "opname_no": opname.opname_no}, "Stok opname selesai")


# ==================== PURCHASES ====================

@inventory_bp.route("/purchases", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_purchase():
    data = request.get_json() or {}
    items = data.get("items", [])

    if not items:
        return error_response("Item pembelian wajib diisi", 400)

    total_amount = Decimal("0.00")
    for item in items:
        subtotal = Decimal(str(item["quantity"])) * Decimal(str(item["unit_price"]))
        total_amount += subtotal

    purchase = Purchase(
        invoice_no=data.get("invoice_no"),
        supplier_name=data.get("supplier_name"),
        total_amount=total_amount,
        notes=data.get("notes")
    )
    db.session.add(purchase)
    db.session.flush()

    for item in items:
        qty = Decimal(str(item["quantity"]))
        unit_price = Decimal(str(item["unit_price"]))
        subtotal = qty * unit_price

        p_item = PurchaseItem(
            purchase_id=purchase.id,
            ingredient_id=item["ingredient_id"],
            quantity=qty,
            unit_price=unit_price,
            subtotal=subtotal
        )
        db.session.add(p_item)

        # Update last purchase price in ingredient
        ing = Ingredient.query.get(item["ingredient_id"])
        if ing:
            ing.last_purchase_price = unit_price

        # Add stock movement
        record_stock_movement(
            ingredient_id=item["ingredient_id"],
            movement_type="PURCHASE",
            quantity=qty,
            reference_type="PURCHASE",
            reference_id=purchase.id,
            notes=f"Pembelian #{purchase.invoice_no or purchase.id}"
        )

    db.session.commit()
    return api_response({"id": purchase.id, "total_amount": float(purchase.total_amount)}, "Pembelian dicatat", 201)

