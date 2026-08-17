import uuid

from sqlalchemy import Column, String

from .base import Base, EntityMixin


class Customer(EntityMixin, Base):
    """Customer master data (problemstatement.md #16, #18).

    Minimal for now: name (from EntityMixin), contact details. Phase 13
    (Credit Management) will add credit-specific fields (credit limit,
    account) on top of this table via its own migration when built -
    not added now to avoid inventing Phase 13's business rules early.
    Never deleted, only deactivated (EntityMixin.status), since sales
    reference a customer permanently.
    """

    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone = Column(String(32), nullable=True)
    email = Column(String(256), nullable=True)
    address = Column(String(512), nullable=True)

    def __repr__(self) -> str:
        return f"<Customer(name={self.name!r}, status={self.status!r})>"
