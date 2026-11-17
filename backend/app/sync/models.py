from sqlalchemy import (
    Column, String, Boolean, Text, BigInteger, Integer, DateTime, UniqueConstraint
)
from app.extensions import db
from app.common.models import SyncBaseModel, get_utc_now


class Notification(SyncBaseModel):
    __tablename__ = "notifications"

    user_id = Column(String(36), nullable=True, index=True)
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), default="INFO", nullable=False)  # ORDER_PENDING, LOW_STOCK, SYSTEM
    reference_id = Column(String(36), nullable=True, index=True)
    is_read = Column(Boolean, default=False, nullable=False)


class Setting(db.Model):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)


class SyncChange(db.Model):
    __tablename__ = "sync_changes"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_sync_change_user_idempotency"
        ),
    )

    server_version = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True
    )
    user_id = Column(String(36), nullable=True, index=True)
    entity_name = Column(String(50), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    operation = Column(String(20), nullable=False)  # INSERT, UPDATE, DELETE
    payload = Column(Text, nullable=False)  # JSON representation
    idempotency_key = Column(String(64), nullable=True)
    time_drift_detected = Column(Boolean, default=False, nullable=False)
    device_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=get_utc_now, nullable=False, index=True)

