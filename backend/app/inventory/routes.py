from decimal import Decimal, InvalidOperation
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


@inventory_bp.route("/units", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def list_units():
    units = Unit.query_active().order_by(Unit.name).all()
    return api_response([{
        "id": unit.id,
        "name": unit.name,
        "symbol": unit.symbol
    } for unit in units])


@inventory_bp.route("/units", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_unit():
    data = request.get_json() or {}
    name = data.get("name", "")
    symbol = data.get("symbol", "")
    if not isinstance(name, str) or not isinstance(symbol, str):
        return error_response("Nama dan simbol satuan tidak valid", 400)
    name = name.strip()
    symbol = symbol.strip()
    if not name or not symbol:
        return error_response("Nama dan simbol satuan wajib diisi", 400)
    if Unit.query_active().filter(db.func.lower(Unit.symbol) == symbol.lower()).first():
        return error_response("Simbol satuan sudah tersedia", 409)

    unit = Unit(name=name, symbol=symbol)
    db.session.add(unit)
    db.session.commit()
    return api_response({
        "id": unit.id,
        "name": unit.name,
        "symbol": unit.symbol
    }, "Satuan dibuat", 201)


@inventory_bp.route("/units/<unit_id>", methods=["PATCH"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def update_unit(unit_id):
    unit = Unit.query_active().filter_by(id=unit_id).first()
    if not unit:
        return error_response("Satuan tidak ditemukan", 404)

    data = request.get_json() or {}
    name = data.get("name", unit.name)
    symbol = data.get("symbol", unit.symbol)
    if not isinstance(name, str) or not isinstance(symbol, str):
        return error_response("Nama dan simbol satuan tidak valid", 400)
    name = name.strip()
    symbol = symbol.strip()
    if not name or not symbol:
        return error_response("Nama dan simbol satuan wajib diisi", 400)
    duplicate = Unit.query_active().filter(
        db.func.lower(Unit.symbol) == symbol.lower(),
        Unit.id != unit.id
    ).first()
    if duplicate:
        return error_response("Simbol satuan sudah tersedia", 409)

    unit.name = name
    unit.symbol = symbol
    db.session.commit()
    return api_response({"id": unit.id, "name": unit.name, "symbol": unit.symbol}, "Satuan diperbarui")


@inventory_bp.route("/units/<unit_id>", methods=["DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def delete_unit(unit_id):
    unit = Unit.query_active().filter_by(id=unit_id).first()
    if not unit:
        return error_response("Satuan tidak ditemukan", 404)
    if Ingredient.query_active().filter_by(unit_id=unit.id).first():
        return error_response("Satuan masih digunakan oleh bahan baku", 409)
    unit.soft_delete()
    db.session.commit()
    return api_response(None, "Satuan dihapus")


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
    name = str(data.get("name", "")).strip()
    unit_id = data.get("unit_id")
    try:
        min_stock = Decimal(str(data.get("min_stock", 0)))
        last_price = Decimal(str(data.get("last_purchase_price", 0)))
    except (InvalidOperation, TypeError, ValueError):
        return error_response("Stok minimum atau harga beli tidak valid", 400)

    if not name or not unit_id:
        return error_response("Nama dan unit wajib diisi", 400)
    if not min_stock.is_finite() or min_stock < 0 or not last_price.is_finite() or last_price < 0:
        return error_response("Stok minimum dan harga beli tidak boleh negatif", 400)
    if not Unit.query_active().filter_by(id=unit_id).first():
        return error_response("Satuan tidak ditemukan", 404)
    if Ingredient.query_active().filter(db.func.lower(Ingredient.name) == name.lower()).first():
        return error_response("Nama bahan baku sudah tersedia", 409)

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
    movement_type = str(data.get("type", "ADJUSTMENT")).upper()
    try:
        quantity = Decimal(str(data.get("quantity", 0)))
    except (InvalidOperation, TypeError, ValueError):
        return error_response("Jumlah stok tidak valid", 400)
    notes = data.get("notes")

    if not ingredient_id or not quantity.is_finite() or quantity == Decimal("0"):
        return error_response("Bahan baku dan jumlah tidak boleh kosong atau 0", 400)
    if movement_type not in {"ADJUSTMENT", "WASTE"}:
        return error_response("Jenis pergerakan stok tidak valid", 400)
    if movement_type == "WASTE" and quantity > 0:
        return error_response("Jumlah waste harus negatif", 400)
    if not Ingredient.query_active().filter_by(id=ingredient_id).first():
        return error_response("Bahan baku tidak ditemukan", 404)

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

    if not isinstance(items, list) or not items:
        return error_response("Item opname wajib diisi", 400)

    normalized_items = []
    seen_ingredients = set()
    for item in items:
        if not isinstance(item, dict):
            return error_response("Format item opname tidak valid", 400)
        ingredient_id = item.get("ingredient_id")
        try:
            actual_qty = Decimal(str(item.get("actual_stock")))
        except (InvalidOperation, TypeError, ValueError):
            return error_response("Jumlah stok opname tidak valid", 400)
        if not ingredient_id or not actual_qty.is_finite() or actual_qty < 0:
            return error_response("Bahan baku dan stok aktual tidak valid", 400)
        if ingredient_id in seen_ingredients:
            return error_response("Bahan baku tidak boleh dicatat dua kali dalam satu opname", 400)
        if not Ingredient.query_active().filter_by(id=ingredient_id).first():
            return error_response("Bahan baku tidak ditemukan", 404)
        seen_ingredients.add(ingredient_id)
        normalized_items.append((ingredient_id, actual_qty))

    opname_no = f"OPN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    opname = StockOpname(opname_no=opname_no, notes=notes)
    db.session.add(opname)
    db.session.flush()

    for ing_id, actual_qty in normalized_items:
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

    if not isinstance(items, list) or not items:
        return error_response("Item pembelian wajib diisi", 400)

    normalized_items = []
    total_amount = Decimal("0.00")
    for item in items:
        if not isinstance(item, dict):
            return error_response("Format item pembelian tidak valid", 400)
        try:
            ingredient_id = item.get("ingredient_id")
            qty = Decimal(str(item.get("quantity")))
            unit_price = Decimal(str(item.get("unit_price")))
        except (InvalidOperation, TypeError, ValueError):
            return error_response("Kuantitas atau harga pembelian tidak valid", 400)
        if not ingredient_id or not qty.is_finite() or qty <= 0 or not unit_price.is_finite() or unit_price < 0:
            return error_response("Bahan, kuantitas positif, dan harga valid wajib diisi", 400)
        ingredient = Ingredient.query_active().filter_by(id=ingredient_id).first()
        if not ingredient:
            return error_response("Bahan baku tidak ditemukan", 404)
        subtotal = qty * unit_price
        total_amount += subtotal
        normalized_items.append((ingredient, qty, unit_price, subtotal))

    purchase = Purchase(
        invoice_no=data.get("invoice_no"),
        supplier_name=data.get("supplier_name"),
        total_amount=total_amount,
        notes=data.get("notes")
    )
    db.session.add(purchase)
    db.session.flush()

    for ingredient, qty, unit_price, subtotal in normalized_items:
        p_item = PurchaseItem(
            purchase_id=purchase.id,
            ingredient_id=ingredient.id,
            quantity=qty,
            unit_price=unit_price,
            subtotal=subtotal
        )
        db.session.add(p_item)

        # Update last purchase price in ingredient
        ingredient.last_purchase_price = unit_price

        # Add stock movement
        record_stock_movement(
            ingredient_id=ingredient.id,
            movement_type="PURCHASE",
            quantity=qty,
            reference_type="PURCHASE",
            reference_id=purchase.id,
            notes=f"Pembelian #{purchase.invoice_no or purchase.id}"
        )

    db.session.commit()
    return api_response({"id": purchase.id, "total_amount": float(purchase.total_amount)}, "Pembelian dicatat", 201)
