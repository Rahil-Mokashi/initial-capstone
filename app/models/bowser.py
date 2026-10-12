"""The bowser van (site visit 2026-10-12): diesel delivered to clients all day on bills with a transport charge.

It is filled from the pump as a "Stock Transfer": recorded as a CREDIT sale through the normal sale
service to an internal customer (so the fuel leaves the tank, counts in the nozzle meters' Total Sale and
the cash remainder shrinks), and linked here by BowserTransfer. Bowser customers are ordinary credit
customers; their bills (with transport) join the same history and ageing (Track 3).

Rows are never edited or deleted. A mistaken bill/reading/opening is VOIDED (status + reason + time).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base


class BowserTransfer(Base):
    """Fuel moved from the pump to the bowser: the link to the credit sale that recorded it."""

    __tablename__ = "bowser_transfers"
    __table_args__ = (CheckConstraint("litres > 0", name="ck_bowser_transfers_litres_positive"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sale_id = Column(String(36), ForeignKey("sales.id"), nullable=False, unique=True)
    transfer_date = Column(Date, nullable=False, index=True)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False, index=True)
    litres = Column(Numeric(12, 3), nullable=False)
    rate = Column(Numeric(10, 2), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    sale = relationship("Sale")
    shift = relationship("Shift")


class BowserBill(Base):
    """One delivery bill: Amount = Qty x rate (paise), Total = Amount + Transport."""

    __tablename__ = "bowser_bills"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_bowser_bills_quantity_positive"),
        CheckConstraint("rate >= 0", name="ck_bowser_bills_rate_non_negative"),
        CheckConstraint("transport >= 0", name="ck_bowser_bills_transport_non_negative"),
        CheckConstraint("total = amount + transport", name="ck_bowser_bills_total_is_amount_plus_transport"),
        CheckConstraint("status IN ('active','void')", name="ck_bowser_bills_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bill_no = Column(String(32), nullable=False, index=True)
    bill_date = Column(Date, nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    quantity = Column(Numeric(12, 3), nullable=False)
    rate = Column(Numeric(10, 2), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    transport = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False)
    vehicle_no = Column(String(32), nullable=True)
    slip_no = Column(String(64), nullable=True)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=True)
    status = Column(String(8), nullable=False, default="active")
    void_reason = Column(Text, nullable=True)
    voided_at = Column(UtcDateTime, nullable=True)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    customer = relationship("Customer")


class BowserMeterReading(Base):
    """The bowser's own meter for one day: Net Sale = End - Start - Testing."""

    __tablename__ = "bowser_meter_readings"
    __table_args__ = (
        CheckConstraint("end_reading >= start_reading", name="ck_bowser_meter_end_not_before_start"),
        CheckConstraint("testing >= 0", name="ck_bowser_meter_testing_non_negative"),
        CheckConstraint("status IN ('active','void')", name="ck_bowser_meter_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reading_date = Column(Date, nullable=False, index=True)
    start_reading = Column(Numeric(14, 3), nullable=False)
    testing = Column(Numeric(12, 3), nullable=False, default=0)
    end_reading = Column(Numeric(14, 3), nullable=False)
    status = Column(String(8), nullable=False, default="active")
    void_reason = Column(Text, nullable=True)
    voided_at = Column(UtcDateTime, nullable=True)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class BowserOpening(Base):
    """A manual opening stock for the bowser (first day, or a correction). Otherwise yesterday's closing carries."""

    __tablename__ = "bowser_openings"
    __table_args__ = (
        CheckConstraint("litres >= 0", name="ck_bowser_openings_litres_non_negative"),
        CheckConstraint("rupees >= 0", name="ck_bowser_openings_rupees_non_negative"),
        CheckConstraint("status IN ('active','void')", name="ck_bowser_openings_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    opening_date = Column(Date, nullable=False, index=True)
    litres = Column(Numeric(12, 3), nullable=False)
    rupees = Column(Numeric(12, 2), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(8), nullable=False, default="active")
    voided_at = Column(UtcDateTime, nullable=True)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
