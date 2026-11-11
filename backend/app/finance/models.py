from sqlalchemy import Column, String, Numeric, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.extensions import db
from app.common.models import SyncBaseModel, get_utc_now


class ExpenseCategory(SyncBaseModel):
    __tablename__ = "expense_categories"

    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    expenses = relationship("Expense", back_populates="category")


class Expense(SyncBaseModel):
    __tablename__ = "expenses"

    category_id = Column(String(36), ForeignKey("expense_categories.id"), nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    notes = Column(Text, nullable=True)
    receipt_image_url = Column(String(255), nullable=True)
    expense_date = Column(DateTime, default=get_utc_now, nullable=False)
    shift_id = Column(String(36), ForeignKey("cash_shifts.id"), nullable=True, index=True)

    category = relationship("ExpenseCategory", back_populates="expenses")
    shift = relationship("CashShift", back_populates="expenses")


class CashShift(SyncBaseModel):
    __tablename__ = "cash_shifts"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(String(64), nullable=True)
    opened_at = Column(DateTime, default=get_utc_now, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    starting_cash = Column(Numeric(15, 2), default=0.00, nullable=False)
    ending_cash_expected = Column(Numeric(15, 2), default=0.00, nullable=False)
    ending_cash_actual = Column(Numeric(15, 2), default=0.00, nullable=False)
    cash_difference = Column(Numeric(15, 2), default=0.00, nullable=False)  # actual - expected
    status = Column(String(20), default="OPEN", nullable=False)  # OPEN, CLOSED

    user = relationship("app.auth.models.User")
    movements = relationship("CashMovement", back_populates="shift", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="shift")


class CashMovement(SyncBaseModel):
    __tablename__ = "cash_movements"

    shift_id = Column(String(36), ForeignKey("cash_shifts.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False)  # CASH_IN, CASH_OUT
    amount = Column(Numeric(15, 2), nullable=False)
    notes = Column(Text, nullable=True)

    shift = relationship("CashShift", back_populates="movements")
