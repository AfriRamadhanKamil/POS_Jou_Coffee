import hashlib
from decimal import Decimal
from datetime import datetime, timezone
from app.extensions import db
from app.inventory.models import (
    StockMovement, StockBalance, Recipe, Ingredient
)


class InsufficientStockError(ValueError):
    pass


def _stock_idempotency_key(*parts):
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


def _required_stock_for_order(order):
    required_by_ingredient = {}
    for item in order.items:
        recipe = Recipe.query_active().filter_by(
            menu_id=item.menu_id,
            variant_id=item.variant_id
        ).first()
        if not recipe and item.variant_id:
            recipe = Recipe.query_active().filter_by(
                menu_id=item.menu_id,
                variant_id=None
            ).first()
        if recipe:
            for recipe_item in recipe.items:
                required_by_ingredient[recipe_item.ingredient_id] = (
                    required_by_ingredient.get(
                        recipe_item.ingredient_id,
                        Decimal("0.0000")
                    )
                    + recipe_item.quantity * Decimal(str(item.quantity))
                )
    return required_by_ingredient


def validate_stock_for_order(order):
    """Checks aggregate recipe demand without changing stock."""
    required_by_ingredient = _required_stock_for_order(order)
    for ingredient_id, required_quantity in required_by_ingredient.items():
        balance = StockBalance.query.filter_by(
            ingredient_id=ingredient_id
        ).with_for_update().first()
        if not balance or balance.current_stock < required_quantity:
            raise InsufficientStockError(
                f"Stok bahan {ingredient_id} tidak mencukupi"
            )


def reserve_stock_for_order(order):
    """Reduces available stock while a QRIS charge is pending."""
    existing = StockMovement.query.filter_by(
        reference_type="ORDER_PAYMENT_RESERVATION",
        reference_id=order.id
    ).first()
    if existing:
        return

    required_by_ingredient = _required_stock_for_order(order)
    balances = {}
    for ingredient_id, required_quantity in required_by_ingredient.items():
        balance = StockBalance.query.filter_by(
            ingredient_id=ingredient_id
        ).with_for_update().first()
        if not balance or balance.current_stock < required_quantity:
            raise InsufficientStockError(
                f"Stok bahan {ingredient_id} tidak mencukupi"
            )
        balances[ingredient_id] = required_quantity

    for ingredient_id, required_quantity in balances.items():
        record_stock_movement(
            ingredient_id=ingredient_id,
            movement_type="PAYMENT_RESERVATION",
            quantity=-required_quantity,
            reference_type="ORDER_PAYMENT_RESERVATION",
            reference_id=order.id,
            notes=f"Reservasi QRIS #{order.order_no}",
            idempotency_key=_stock_idempotency_key(
                "order-payment-reservation", order.id, ingredient_id
            ),
            created_by=order.created_by
        )


def release_stock_reservation(order):
    reservations = StockMovement.query.filter_by(
        reference_type="ORDER_PAYMENT_RESERVATION",
        reference_id=order.id
    ).all()
    for reservation in reservations:
        record_stock_movement(
            ingredient_id=reservation.ingredient_id,
            movement_type="PAYMENT_RESERVATION_RELEASE",
            quantity=-reservation.quantity,
            reference_type="ORDER_PAYMENT_RESERVATION_RELEASE",
            reference_id=order.id,
            notes=f"Reservasi QRIS dibatalkan #{order.order_no}",
            idempotency_key=_stock_idempotency_key(
                "order-payment-reservation-release", reservation.id
            ),
            created_by=order.created_by
        )


def has_stock_reservation(order):
    return StockMovement.query.filter_by(
        reference_type="ORDER_PAYMENT_RESERVATION",
        reference_id=order.id
    ).first() is not None


def record_stock_movement(ingredient_id: str, movement_type: str, quantity: Decimal,
                          reference_type: str = None, reference_id: str = None,
                          notes: str = None, idempotency_key: str = None,
                          created_by: str = None):
    """
    Append-only stock ledger operation.
    Updates or creates stock_balances cache.
    Quantity is positive for additions (PURCHASE, OPNAME_PLUS, VOID_REVERSAL)
    and negative for deductions (SALE, WASTE, OPNAME_MINUS).
    """
    if idempotency_key:
        existing = StockMovement.query.filter_by(
            idempotency_key=idempotency_key
        ).first()
        if existing:
            if (
                existing.ingredient_id != ingredient_id
                or existing.type != movement_type
                or existing.quantity != quantity
            ):
                raise ValueError("Idempotency key stok sudah dipakai untuk perubahan lain")
            return existing

    balance = StockBalance.query.filter_by(ingredient_id=ingredient_id).with_for_update().first()
    if not balance:
        balance = StockBalance(ingredient_id=ingredient_id, current_stock=Decimal("0.0000"))
        db.session.add(balance)

    new_stock = balance.current_stock + quantity
    if new_stock < 0:
        raise InsufficientStockError(
            f"Stok bahan {ingredient_id} tidak mencukupi"
        )
    balance.current_stock = new_stock
    balance.last_updated_at = datetime.now(timezone.utc)

    movement = StockMovement(
        ingredient_id=ingredient_id,
        type=movement_type,
        quantity=quantity,
        balance_after=new_stock,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        idempotency_key=idempotency_key,
        created_by=created_by
    )
    db.session.add(movement)
    return movement


def deduct_stock_for_order(order):
    """
    Deducts ingredients according to recipe (BOM) for each item in the order.
    Called when order is APPROVED.
    """
    if has_stock_reservation(order):
        return

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
                    notes=f"Penjualan #{order.order_no} ({item.item_name})",
                    idempotency_key=_stock_idempotency_key(
                        "order-sale", order.id, item.id, r_item.id
                    ),
                    created_by=order.created_by
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
                    notes=f"Void #{order.order_no} ({item.item_name})",
                    idempotency_key=_stock_idempotency_key(
                        "order-void", order.id, item.id, r_item.id
                    ),
                    created_by=order.created_by
                )


def calculate_recipe_cogs(recipe: Recipe) -> Decimal:
    """Calculates COGS (HPP) of a recipe based on ingredients' last purchase prices."""
    total_cogs = Decimal("0.00")
    for r_item in recipe.items:
        ing = r_item.ingredient
        if ing:
            total_cogs += r_item.quantity * ing.last_purchase_price
    return total_cogs

