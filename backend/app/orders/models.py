from sqlalchemy import Column, String, Boolean, Numeric, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.extensions import db
from app.common.models import SyncBaseModel, get_utc_now


# Order status constants
STATUS_AWAITING_PAYMENT = "AWAITING_PAYMENT"
STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
STATUS_APPROVED = "APPROVED"
STATUS_PREPARING = "PREPARING"
STATUS_READY = "READY"
STATUS_COMPLETED = "COMPLETED"
STATUS_REJECTED = "REJECTED"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELLED = "CANCELLED"

# Payment status constants
PAYMENT_UNPAID = "UNPAID"
PAYMENT_PAID = "PAID"
PAYMENT_REFUNDED = "REFUNDED"

# Order source constants
SOURCE_POS = "POS"
SOURCE_QR = "QR"
SOURCE_ONLINE = "ONLINE_PLATFORM"

# Order type constants
TYPE_DINE_IN = "DINE_IN"
TYPE_TAKE_AWAY = "TAKE_AWAY"
TYPE_DELIVERY = "DELIVERY"


class Table(SyncBaseModel):
    __tablename__ = "tables"

    table_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=True)  # e.g., Meja 1, Meja Bar
    qr_token = Column(String(255), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)


class Order(SyncBaseModel):
    __tablename__ = "orders"

    order_no = Column(String(50), unique=True, nullable=False, index=True)
    source = Column(String(30), default=SOURCE_POS, nullable=False)  # POS, QR, ONLINE_PLATFORM
    order_type = Column(String(30), default=TYPE_DINE_IN, nullable=False)  # DINE_IN, TAKE_AWAY, DELIVERY
    table_id = Column(String(36), ForeignKey("tables.id"), nullable=True, index=True)
    channel_id = Column(String(36), ForeignKey("sales_channels.id"), nullable=True, index=True)
    external_order_id = Column(String(100), nullable=True, index=True)
    status = Column(String(30), default=STATUS_APPROVED, nullable=False, index=True)
    payment_status = Column(String(20), default=PAYMENT_UNPAID, nullable=False, index=True)
    
    subtotal = Column(Numeric(15, 2), default=0.00, nullable=False)
    discount = Column(Numeric(15, 2), default=0.00, nullable=False)
    platform_commission = Column(Numeric(15, 2), default=0.00, nullable=False)
    total = Column(Numeric(15, 2), default=0.00, nullable=False)
    
    customer_name = Column(String(100), nullable=True)
    shift_id = Column(String(36), nullable=True, index=True)
    approved_by = Column(String(36), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    idempotency_key = Column(String(64), unique=True, nullable=True, index=True)

    table = relationship("Table")
    channel = relationship("app.catalog.models.SalesChannel")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    status_logs = relationship("OrderStatusLog", back_populates="order", cascade="all, delete-orphan")


class OrderItem(SyncBaseModel):
    __tablename__ = "order_items"

    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    menu_id = Column(String(36), ForeignKey("menus.id"), nullable=False, index=True)
    variant_id = Column(String(36), ForeignKey("menu_variants.id"), nullable=True, index=True)
    item_name = Column(String(150), nullable=False)
    quantity = Column(Numeric(15, 4), default=1.0000, nullable=False)
    unit_price = Column(Numeric(15, 2), default=0.00, nullable=False)
    discount = Column(Numeric(15, 2), default=0.00, nullable=False)
    subtotal = Column(Numeric(15, 2), default=0.00, nullable=False)
    notes = Column(Text, nullable=True)

    order = relationship("Order", back_populates="items")
    menu = relationship("app.catalog.models.Menu")
    variant = relationship("app.catalog.models.MenuVariant")
    modifiers = relationship("OrderItemModifier", back_populates="order_item", cascade="all, delete-orphan")


class OrderItemModifier(SyncBaseModel):
    __tablename__ = "order_item_modifiers"

    order_item_id = Column(String(36), ForeignKey("order_items.id"), nullable=False, index=True)
    modifier_id = Column(String(36), ForeignKey("modifiers.id"), nullable=False, index=True)
    modifier_name = Column(String(100), nullable=False)
    price = Column(Numeric(15, 2), default=0.00, nullable=False)

    order_item = relationship("OrderItem", back_populates="modifiers")
    modifier = relationship("app.catalog.models.Modifier")


class Payment(SyncBaseModel):
    __tablename__ = "payments"

    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    payment_method = Column(String(30), nullable=False)  # TUNAI, QRIS_STATIS, QRIS_DINAMIS, PLATFORM
    amount = Column(Numeric(15, 2), nullable=False)
    change_amount = Column(Numeric(15, 2), default=0.00, nullable=False)
    status = Column(String(20), default=PAYMENT_PAID, nullable=False)  # PAID, REFUNDED
    provider = Column(String(50), nullable=True)  # e.g., midtrans, xendit, doku
    provider_ref = Column(String(100), nullable=True, index=True)
    paid_at = Column(DateTime, default=get_utc_now)
    raw_webhook = Column(Text, nullable=True)

    order = relationship("Order", back_populates="payments")


class OrderStatusLog(SyncBaseModel):
    __tablename__ = "order_status_logs"

    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=False)
    changed_by = Column(String(36), nullable=True)
    notes = Column(Text, nullable=True)

    order = relationship("Order", back_populates="status_logs")

