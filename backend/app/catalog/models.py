from sqlalchemy import Column, String, Boolean, Integer, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.extensions import db
from app.common.models import SyncBaseModel


class Category(SyncBaseModel):
    __tablename__ = "categories"

    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    menus = relationship("Menu", back_populates="category", cascade="all, delete-orphan")


class Menu(SyncBaseModel):
    __tablename__ = "menus"

    category_id = Column(String(36), ForeignKey("categories.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(255), nullable=True)
    base_price = Column(Numeric(15, 2), default=0.00, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)  # False if ingredients run out

    category = relationship("Category", back_populates="menus")
    variants = relationship("MenuVariant", back_populates="menu", cascade="all, delete-orphan")
    recipes = relationship("Recipe", back_populates="menu", cascade="all, delete-orphan")
    channel_prices = relationship("MenuChannelPrice", back_populates="menu", cascade="all, delete-orphan")


class MenuVariant(SyncBaseModel):
    __tablename__ = "menu_variants"

    menu_id = Column(String(36), ForeignKey("menus.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # e.g., Regular, Large, Hot, Iced
    price_adjustment = Column(Numeric(15, 2), default=0.00, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    menu = relationship("Menu", back_populates="variants")


class ModifierGroup(SyncBaseModel):
    __tablename__ = "modifier_groups"

    name = Column(String(100), nullable=False)  # e.g., Sugar Level, Topping, Dairy Choice
    min_selection = Column(Integer, default=0, nullable=False)
    max_selection = Column(Integer, default=1, nullable=False)
    is_required = Column(Boolean, default=False, nullable=False)

    modifiers = relationship("Modifier", back_populates="group", cascade="all, delete-orphan")


class Modifier(SyncBaseModel):
    __tablename__ = "modifiers"

    group_id = Column(String(36), ForeignKey("modifier_groups.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    price = Column(Numeric(15, 2), default=0.00, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    group = relationship("ModifierGroup", back_populates="modifiers")


class SalesChannel(SyncBaseModel):
    __tablename__ = "sales_channels"

    name = Column(String(100), nullable=False)  # e.g., Dine In, Take Away, GoFood, GrabFood, ShopeeFood
    code = Column(String(50), unique=True, nullable=False)
    commission_percent = Column(Numeric(5, 2), default=0.00, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    channel_prices = relationship("MenuChannelPrice", back_populates="channel", cascade="all, delete-orphan")


class MenuChannelPrice(SyncBaseModel):
    __tablename__ = "menu_channel_prices"

    menu_id = Column(String(36), ForeignKey("menus.id"), nullable=False, index=True)
    channel_id = Column(String(36), ForeignKey("sales_channels.id"), nullable=False, index=True)
    price = Column(Numeric(15, 2), nullable=False)

    menu = relationship("Menu", back_populates="channel_prices")
    channel = relationship("SalesChannel", back_populates="channel_prices")
