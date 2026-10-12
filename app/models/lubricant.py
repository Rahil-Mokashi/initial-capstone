"""Lubricants (HP Racer, Milcy Turbo, ...): sold and stocked per item (site visit 2026-10-12, K-09).

This is a NEW module beside fuel. The older "fuel only, no other retail" rule (PROJECT_CONTEXT.md,
2026-08-18) is contradicted by the owner's own daily report, whose Oil sale table feeds "Total Sale";
that rule is left as history and not edited.

LubricantMovement is append-only (the project's VOID/REVERSE/ADJUST-not-DELETE rule): stock on any
date is the sum of opening + purchase + adjustment rows, less sales, up to that date. A mistake is
corrected with a signed 'adjustment' that carries a reason, never by editing a row.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base, EntityMixin

MOVEMENT_KINDS = ("opening", "purchase", "sale", "adjustment")


class LubricantItem(EntityMixin, Base):
    __tablename__ = "lubricant_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # e.g. "1 ltr", "500 ml", "5 ltr": how the item is sold. The item name itself is EntityMixin.name.
    pack_size = Column(String(32), nullable=True)
    default_rate = Column(Numeric(10, 2), nullable=False, default=0)

    __table_args__ = (CheckConstraint("default_rate >= 0", name="ck_lubricant_items_rate_non_negative"),)


class LubricantMovement(Base):
    __tablename__ = "lubricant_movements"
    __table_args__ = (
        CheckConstraint("kind IN ('opening','purchase','sale','adjustment')", name="ck_lubricant_movements_kind"),
        CheckConstraint("kind = 'adjustment' OR quantity > 0", name="ck_lubricant_movements_quantity_positive"),
        CheckConstraint("quantity != 0", name="ck_lubricant_movements_quantity_non_zero"),
        CheckConstraint("unit_rate IS NULL OR unit_rate >= 0", name="ck_lubricant_movements_rate_non_negative"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id = Column(String(36), ForeignKey("lubricant_items.id"), nullable=False, index=True)
    movement_date = Column(Date, nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    # Units (a pack, or litres for loose oil). Positive, except an adjustment which is signed.
    quantity = Column(Numeric(12, 3), nullable=False)
    # Sale: the selling rate. Purchase: the cost per unit (optional).
    unit_rate = Column(Numeric(10, 2), nullable=True)
    # Sale only: quantity x rate settled once to paise (app/core/money.py), stored so reports never recompute it.
    amount = Column(Numeric(12, 2), nullable=True)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=True, index=True)
    customer_name = Column(String(255), nullable=True)
    remarks = Column(Text, nullable=True)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    item = relationship("LubricantItem")
    shift = relationship("Shift")
    recorded_by = relationship("User")
