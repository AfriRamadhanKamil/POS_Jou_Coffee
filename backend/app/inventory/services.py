from decimal import Decimal
from datetime import datetime, timezone
from app.extensions import db
from app.inventory.models import (
    StockMovement, StockBalance, Recipe, Ingredient
)


def record_stock_movement(ingredient_id: str, movement_type: str, quantity: Decimal,
                          reference_type: str = None, reference_id: str = None, notes: str = None):
    """
    Append-only stock ledger operation.
    Updates or creates stock_balances cache.
    Quantity is positive for additions (PURCHASE, OPNAME_PLUS, VOID_REVERSAL)
    and negative for deductions (SALE, WASTE, OPNAME_MINUS).
    """
    balance = StockBalance.query.filter_by(ingredient_id=ingredient_id).with_for_update().first()
    if not balance:
        balance = StockBalance(ingredient_id=ingredient_id, current_stock=Decimal("0.0000"))
        db.session.add(balance)

    new_stock = balance.current_stock + quantity
    balance.current_stock = new_stock
    balance.last_updated_at = datetime.now(timezone.utc)

    movement = StockMovement(
        ingredient_id=ingredient_id,
        type=movement_type,
        quantity=quantity,
        balance_after=new_stock,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes
    )
    db.session.add(movement)
    return movement


def deduct_stock_for_order(order):
    """
    Deducts ingredients according to recipe (BOM) for each item in the order.
    Called when order is APPROVED.
    """
    for item in order.items:
        # Find recipe for menu_id and optional variant_id
        recipe = Recipe.query_active().filter_by(
            menu_id=item.menu_id,
            variant_id=item.variant_id
        ).first()

        # Fallback to menu recipe without variant if not found
        if not recipe and item.variant_id:
            recipe = Recipe.query_active().filter_by(menu_id=item.menu_id, variant_id=None).first()

        if recipe:
            for r_item in recipe.items:
                deduction_qty = -1 * (r_item.quantity * Decimal(str(item.quantity)))
                record_stock_movement(
                    ingredient_id=r_item.ingredient_id,
                    movement_type="SALE",
                    quantity=deduction_qty,
                    reference_type="ORDER",
                    reference_id=order.id,
                    notes=f"Penjualan #{order.order_no} ({item.item_name})"
                )


def return_stock_for_void(order):
    """
    Restores stock via reverse movement (VOID_REVERSAL).
    Called when order is VOID / CANCELLED.
    """
    for item in order.items:
        recipe = Recipe.query_active().filter_by(
            menu_id=item.menu_id,
            variant_id=item.variant_id
        ).first()
        if not recipe and item.variant_id:
            recipe = Recipe.query_active().filter_by(menu_id=item.menu_id, variant_id=None).first()

        if recipe:
            for r_item in recipe.items:
                reversal_qty = r_item.quantity * Decimal(str(item.quantity))
                record_stock_movement(
                    ingredient_id=r_item.ingredient_id,
                    movement_type="VOID_REVERSAL",
                    quantity=reversal_qty,
                    reference_type="ORDER_VOID",
                    reference_id=order.id,
                    notes=f"Void #{order.order_no} ({item.item_name})"
                )


def calculate_recipe_cogs(recipe: Recipe) -> Decimal:
    """Calculates COGS (HPP) of a recipe based on ingredients' last purchase prices."""
    total_cogs = Decimal("0.00")
    for r_item in recipe.items:
        ing = r_item.ingredient
        if ing:
            total_cogs += r_item.quantity * ing.last_purchase_price
    return total_cogs

