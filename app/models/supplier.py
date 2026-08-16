import uuid

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from .base import Base, EntityMixin


class Supplier(EntityMixin, Base):
    """Fuel supplier master data (problemstatement.md #12, #23).

    EntityMixin's `name` column is the supplier's business name; status
    (active/inactive) controls whether new purchase orders can be raised
    against them — a supplier is never deleted, only deactivated, since
    historical purchase orders/invoices must keep referencing it.
    """

    __tablename__ = "suppliers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contact_person = Column(String(128), nullable=True)
    phone = Column(String(32), nullable=True)
    email = Column(String(256), nullable=True)
    address = Column(String(512), nullable=True)
    gst_number = Column(String(32), nullable=True)

    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")

    def __repr__(self) -> str:
        return f"<Supplier(name={self.name!r}, status={self.status!r})>"
