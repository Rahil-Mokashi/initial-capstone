import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class FuelDelivery(Base):
    """One tanker delivery against a purchase order (problemstatement.md
    #12): Tanker Arrival -> Document Verification -> Fuel Quality
    Verification -> Pre-Dip Reading -> Fuel Unloading -> Post-Dip Reading
    -> Inventory Update. Each dip reading also creates a real TankReading
    (via TankService), and unloading creates a real TankTransaction
    RECEIPT (also via TankService) - a delivery never moves tank stock on
    its own, it always goes through the same tank machinery every other
    receipt does. quantity_received is derived (post_dip - pre_dip), not
    entered directly, so it can't drift from what was actually dipped.
    """

    __tablename__ = "fuel_deliveries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    purchase_order_id = Column(String(36), ForeignKey("purchase_orders.id"), nullable=False, index=True)
    tank_id = Column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)

    # The employee physically on-site taking dip readings (TankReading's
    # own employee_id) is not necessarily the logged-in User operating
    # the software (recorded_by_id below) - same actor/employee split
    # used by Shift/NozzleAssignment elsewhere in this app.
    received_by_employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False)

    tanker_number = Column(String(32), nullable=False)
    driver_name = Column(String(128), nullable=True)
    arrived_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    status = Column(String(32), nullable=False)

    document_verified_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    document_verified_at = Column(DateTime, nullable=True)

    quality_verified_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    quality_verified_at = Column(DateTime, nullable=True)
    quality_notes = Column(Text, nullable=True)

    pre_dip_value = Column(Numeric(12, 3), nullable=True)
    pre_dip_reading_id = Column(String(36), ForeignKey("tank_readings.id"), nullable=True)

    post_dip_value = Column(Numeric(12, 3), nullable=True)
    post_dip_reading_id = Column(String(36), ForeignKey("tank_readings.id"), nullable=True)

    quantity_received = Column(Numeric(12, 3), nullable=True)
    tank_transaction_id = Column(String(36), ForeignKey("tank_transactions.id"), nullable=True)

    rejection_reason = Column(Text, nullable=True)

    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    remarks = Column(Text, nullable=True)

    purchase_order = relationship("PurchaseOrder", back_populates="deliveries")
    tank = relationship("Tank")
    received_by_employee = relationship("Employee")
    document_verified_by = relationship("User", foreign_keys=[document_verified_by_id])
    quality_verified_by = relationship("User", foreign_keys=[quality_verified_by_id])
    recorded_by = relationship("User", foreign_keys=[recorded_by_id])
    pre_dip_reading = relationship("TankReading", foreign_keys=[pre_dip_reading_id])
    post_dip_reading = relationship("TankReading", foreign_keys=[post_dip_reading_id])
    tank_transaction = relationship("TankTransaction")

    def __repr__(self) -> str:
        return f"<FuelDelivery(tanker_number={self.tanker_number!r}, status={self.status!r})>"
