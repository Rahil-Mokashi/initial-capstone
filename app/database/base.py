"""
Base model class for SQLAlchemy ORM in Petrol Pump ERP.

Provides common mixins and utilities for all domain models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from sqlalchemy import Column, DateTime, String, Text, Boolean, Integer
from sqlalchemy.orm import deprecated


class StatusEnum(str, Enum):
    """Status enumeration for various entities."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    CANCELLED = "cancelled"


class EntityMixin:
    """
    Mixin providing common fields and methods for all entities.
    """

    # Timestamps
    created_at: Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Status field
    status: Column(String, default="active")

    # Soft delete flag
    is_deleted: Column(Boolean, default=False)

    # Human-readable name
    name: Column(String, nullable=False)

    # Relationship helper
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r}, status={self.status!r})>"


# Import here to avoid circular imports
from .connection import engine, SessionLocal


# Core domain models will inherit from EntityMixin
# Example:
# class User(EntityMixin):
#     __tablename__ = "users"
#     id: Column(Integer, primary_key=True, index=True)
#     username: Column(String, unique=True, index=True)
#     email: Column(String, unique=True, index=True)
#     password_hash: Column(String, nullable=False)
#     is_active: Column(Boolean, default=True)
#     role: Column(String, default="attendant")
#     created_at: Column(DateTime, default=datetime.utcnow)
#     updated_at: Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
#     is_deleted: Column(Boolean, default=False)
#
# class Role(EntityMixin):
#     __tablename__ = "roles"
#     id: Column(Integer, primary_key=True, index=True)
#     name: Column(String, unique=True, index=True)
#     description: Column(Text)
#
# class Permission(EntityMixin):
#     __tablename__ = "permissions"
#     id: Column(Integer, primary_key=True, index=True)
#     name: Column(String, unique=True, index=True)
#     description: Column(Text)
#
# class Employee(EntityMixin):
#     __tablename__ = "employees"
#     id: Column(Integer, primary_key=True, index=True)
#     first_name: Column(String, nullable=False)
#     last_name: Column(String, nullable=False)
#     employee_id: Column(String, unique=True, index=True)
#     role_id: Column(Integer, ForeignKey("roles.id"))
#     hire_date: Column(DateTime)
#     status: Column(String, default="active")
#     is_deleted: Column(Boolean, default=False)
#
# class Shift(EntityMixin):
#     __tablename__ = "shifts"
#     id: Column(Integer, primary_key=True, index=True)
#     start_time: Column(DateTime, nullable=False)
#     end_time: Column(DateTime, nullable=False)
#     shift_type: Column(String, nullable=False)  # e.g., "day", "night"
#     is_active: Column(Boolean, default=True)
#
# class Nozzle(EntityMixin):
#     __tablename__ = "nozzles"
#     id: Column(Integer, primary_key=True, index=True)
#     name: Column(String, nullable=False)
#     fuel_type: Column(String, nullable=False)
#     capacity_liters: Column(Integer, nullable=False)
#     is_active: Column(Boolean, default=True)
#
# class Tank(EntityMixin):
#     __tablename__ = "tanks"
#     id: Column(Integer, primary_key=True, index=True)
#     name: Column(String, nullable=False)
#     capacity_liters: Column(Integer, nullable=False)
#     current_level_liters: Column(Integer, nullable=False)
#     fuel_type: Column(String, nullable=False)
#
# class Dispenser(EntityMixin):
#     __tablename__ = "dispatchers"
#     id: Column(Integer, primary_key=True, index=True)
#     name: Column(String, nullable=False)
#     fuel_type: Column(String, nullable=False)
#
# class Sale(EntityMixin):
#     __tablename__ = "sales"
#     id: Column(Integer, primary_key=True, index=True)
#     sale_id: Column(String, unique=True, index=True)
#     sale_date: Column(DateTime, nullable=False)
#     total_amount: Column(Integer, nullable=False)  # in paise
#     currency: Column(String, default="INR")
#     status: Column(String, default="completed")
#
# class Payment(EntityMixin):
#     __tablename__ = "payments"
#     id: Column(Integer, primary_key=True, index=True)
#     payment_id: Column(String, unique=True, index=True)
#     sale_id: Column(Integer, ForeignKey("sales.sale_id"))
#     amount: Column(Integer, nullable=False)  # in paise
#     payment_method: Column(String)  # "cash", "upi", "card", "credit"
#     status: Column(String, default="pending")
#     created_at: Column(DateTime, default=datetime.utcnow)
#
# class CreditSale(EntityMixin):
#     __tablename__ = "credit_sales"
#     id: Column(Integer, primary_key=True, index=True)
#     sale_id: Column(Integer, ForeignKey("sales.sale_id"))
#     amount: Column(Integer, nullable=False)  # in paise
#     status: Column(String, default="pending")
#
# class Expense(EntityMixin):
#     __tablename__ = "expenses"
#     id: Column(Integer, primary_key=True, index=True)
#     expense_id: Column(String, unique=True, index=True)
#     expense_type: Column(String)  # "fuel", "supplier", "maintenance", etc.
#     amount: Column(Integer, nullable=False)  # in paise
#     description: Column(Text)
#     date: Column(DateTime, nullable=False)
#     status: Column(String, default="pending")
#
# class Transfer(EntityMixin):
#     __tablename__ = "transfers"
#     id: Column(Integer, primary_key=True, index=True)
#     transfer_id: Column(String, unique=True, index=True)
#     from_employee_id: Column(Integer, ForeignKey("employees.id"))
#     to_employee_id: Column(Integer, ForeignKey("employees.id"))
#     amount: Column(Integer, nullable=False)  # in paise
#     purpose: Column(String)
#     status: Column(String, default="pending")
#     created_at: Column(DateTime, default=datetime.utcnow)
#
# class AuditLog(EntityMixin):
#     __tablename__ = "audit_logs"
#     id: Column(Integer, primary_key=True, index=True)
#     event_type: Column(String)  # "login", "sale", "payment", "transfer", etc.
#     entity_id: Column(Integer, nullable=False)
#     actor_id: Column(Integer, nullable=True)
#     old_value: Column(Text)
#     new_value: Column(Text)
#     timestamp: Column(DateTime, default=datetime.utcnow)
#

__all__ = [
    "EntityMixin",
    "StatusEnum",
    "Base",
]
