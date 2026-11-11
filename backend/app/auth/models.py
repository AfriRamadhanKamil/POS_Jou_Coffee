from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.extensions import db
from app.common.models import SyncBaseModel, get_utc_now


class User(SyncBaseModel):
    __tablename__ = "users"

    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    pin_hash = Column(String(255), nullable=True)  # 6 digit PIN for kasir
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # kasir, admin, super_admin
    is_active = Column(Boolean, default=True, nullable=False)

    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")


class Device(SyncBaseModel):
    __tablename__ = "devices"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(String(64), nullable=False, index=True)
    device_name = Column(String(100), nullable=True)
    is_revoked = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime, default=get_utc_now)

    user = relationship("User", back_populates="devices")


class AuditLog(SyncBaseModel):
    __tablename__ = "audit_logs"

    user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(50), nullable=False)  # VOID, DELETE, PRICE_CHANGE, STOCK_CHANGE, PERMISSION_CHANGE
    entity = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=True)
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)

