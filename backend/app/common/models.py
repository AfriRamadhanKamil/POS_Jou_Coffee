import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, BigInteger, func
from app.extensions import db


def get_utc_now():
    return datetime.now(timezone.utc)


def generate_uuid():
    return str(uuid.uuid4())


class SyncBaseModel(db.Model):
    """
    Abstract base model for synchronized tables.
    Standard columns: id CHAR(36) PK, created_at, updated_at, deleted_at,
    created_by, device_id, server_version BIGINT.
    """
    __abstract__ = True

    id = Column(String(36), primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=get_utc_now, nullable=False, index=True)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete
    created_by = Column(String(36), nullable=True)
    device_id = Column(String(64), nullable=True)
    server_version = Column(BigInteger, nullable=True, index=True)

    def soft_delete(self):
        self.deleted_at = get_utc_now()
        db.session.add(self)

    @classmethod
    def query_active(cls):
        """Query excluding soft-deleted records."""
        return cls.query.filter(cls.deleted_at.is_(None))
