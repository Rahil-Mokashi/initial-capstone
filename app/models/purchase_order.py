import uuid
from datetime import date as date_type
from datetime import datetime, timezone

from sqlalchemy import Column, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class PurchaseOrder(Base):
    """A fuel purchase order raised against a supplier (problemstatement.md
    #12: Fuel Requirement -> Purchase). Line items (fuel type, quantity,
    rate) live in PurchaseOrderItem. Status tracks the order's own
    lifecycle; individual deliveries against it are tracked separately
    in FuelDelivery so a partially-delivered order stays traceable."""

    __tablename__ = "purchase_orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    po_number = Column(String(32), unique=True, nullable=False, index=True)
    supplier_id = Column(String(36), ForeignKey("suppliers.id"), nullable=False, index=True)

    order_date = Column(Date, default=date_type.today, nullable=False)
    expected_delivery_date = Column(Date, nullable=True)
    status = Column(String(32), nullable=False)

    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    remarks = Column(Text, nullable=True)

    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        UtcDateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    supplier = relationship("Supplier", back_populates="purchase_orders")
    created_by = relationship("User")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")
    deliveries = relationship("FuelDelivery", back_populates="purchase_order")

    def __repr__(self) -> str:
        return f"<PurchaseOrder(po_number={self.po_number!r}, status={self.status!r})>"


class PurchaseOrderItem(Base):
    """One fuel-type line item on a purchase order."""

    __tablename__ = "purchase_order_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    purchase_order_id = Column(String(36), ForeignKey("purchase_orders.id"), nullable=False, index=True)
    fuel_id = Column(String(36), ForeignKey("fuels.id"), nullable=False)

    quantity_ordered = Column(Numeric(12, 3), nullable=False)
    rate_per_liter = Column(Numeric(10, 2), nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="items")
    fuel = relationship("Fuel")

    def __repr__(self) -> str:
        return f"<PurchaseOrderItem(fuel_id={self.fuel_id!r}, quantity_ordered={self.quantity_ordered!r})>"
