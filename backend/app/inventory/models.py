from sqlalchemy import Column, String, Boolean, Numeric, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.extensions import db
from app.common.models import SyncBaseModel, get_utc_now


class Unit(SyncBaseModel):
    __tablename__ = "units"

    name = Column(String(50), nullable=False)  # Gram, Milliliter, Pcs, Shot
    symbol = Column(String(20), nullable=False)  # g, ml, pcs, shot


class Ingredient(SyncBaseModel):
    __tablename__ = "ingredients"

    name = Column(String(150), nullable=False)
    unit_id = Column(String(36), ForeignKey("units.id"), nullable=False, index=True)
    min_stock = Column(Numeric(15, 4), default=0.0000, nullable=False)
    last_purchase_price = Column(Numeric(15, 2), default=0.00, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    unit = relationship("Unit")
    movements = relationship("StockMovement", back_populates="ingredient")
    balance = relationship("StockBalance", back_populates="ingredient", uselist=False)


class Recipe(SyncBaseModel):
    __tablename__ = "recipes"

    menu_id = Column(String(36), ForeignKey("menus.id"), nullable=False, index=True)
    variant_id = Column(String(36), ForeignKey("menu_variants.id"), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    menu = relationship("app.catalog.models.Menu", back_populates="recipes")
    variant = relationship("app.catalog.models.MenuVariant")
    items = relationship("RecipeItem", back_populates="recipe", cascade="all, delete-orphan")


class RecipeItem(SyncBaseModel):
    __tablename__ = "recipe_items"

    recipe_id = Column(String(36), ForeignKey("recipes.id"), nullable=False, index=True)
    ingredient_id = Column(String(36), ForeignKey("ingredients.id"), nullable=False, index=True)
    quantity = Column(Numeric(15, 4), nullable=False)  # e.g., 18.0000 grams coffee bean

    recipe = relationship("Recipe", back_populates="items")
    ingredient = relationship("Ingredient")


class StockMovement(SyncBaseModel):
    __tablename__ = "stock_movements"

    ingredient_id = Column(String(36), ForeignKey("ingredients.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    # Types: PURCHASE, SALE, ADJUSTMENT, WASTE, OPNAME, VOID_REVERSAL
    quantity = Column(Numeric(15, 4), nullable=False)  # positive for addition, negative for deduction
    balance_after = Column(Numeric(15, 4), nullable=False)
    reference_type = Column(String(50), nullable=True)  # ORDER, PURCHASE, OPNAME, MANUAL
    reference_id = Column(String(36), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    ingredient = relationship("Ingredient", back_populates="movements")


class StockBalance(SyncBaseModel):
    __tablename__ = "stock_balances"

    ingredient_id = Column(String(36), ForeignKey("ingredients.id"), unique=True, nullable=False, index=True)
    current_stock = Column(Numeric(15, 4), default=0.0000, nullable=False)
    last_updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    ingredient = relationship("Ingredient", back_populates="balance")


class Purchase(SyncBaseModel):
    __tablename__ = "purchases"

    invoice_no = Column(String(100), nullable=True)
    supplier_name = Column(String(150), nullable=True)
    total_amount = Column(Numeric(15, 2), default=0.00, nullable=False)
    purchase_date = Column(DateTime, default=get_utc_now, nullable=False)
    notes = Column(Text, nullable=True)

    items = relationship("PurchaseItem", back_populates="purchase", cascade="all, delete-orphan")


class PurchaseItem(SyncBaseModel):
    __tablename__ = "purchase_items"

    purchase_id = Column(String(36), ForeignKey("purchases.id"), nullable=False, index=True)
    ingredient_id = Column(String(36), ForeignKey("ingredients.id"), nullable=False, index=True)
    quantity = Column(Numeric(15, 4), nullable=False)
    unit_price = Column(Numeric(15, 2), nullable=False)
    subtotal = Column(Numeric(15, 2), nullable=False)

    purchase = relationship("Purchase", back_populates="items")
    ingredient = relationship("Ingredient")


class StockOpname(SyncBaseModel):
    __tablename__ = "stock_opnames"

    opname_no = Column(String(50), unique=True, nullable=False)
    status = Column(String(20), default="COMPLETED", nullable=False)
    notes = Column(Text, nullable=True)

    items = relationship("StockOpnameItem", back_populates="opname", cascade="all, delete-orphan")


class StockOpnameItem(SyncBaseModel):
    __tablename__ = "stock_opname_items"

    opname_id = Column(String(36), ForeignKey("stock_opnames.id"), nullable=False, index=True)
    ingredient_id = Column(String(36), ForeignKey("ingredients.id"), nullable=False, index=True)
    system_stock = Column(Numeric(15, 4), nullable=False)
    actual_stock = Column(Numeric(15, 4), nullable=False)
    difference = Column(Numeric(15, 4), nullable=False)  # actual - system

    opname = relationship("StockOpname", back_populates="items")
    ingredient = relationship("Ingredient")

