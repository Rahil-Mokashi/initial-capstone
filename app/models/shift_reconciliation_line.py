import uuid

from sqlalchemy import Column, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import Base


class ShiftReconciliationLine(Base):
    """One tender's expected/declared/variance for a shift reconciliation
    (ShiftReconciliation). Replaces that model's old fixed cash/upi/card
    columns - see PROJECT_CONTEXT.md's Step 2 entry for why and how the
    migration preserves every existing row's figures.

    Generated automatically for every non-credit tender
    (Tender.settlement_type != INVOICED_CREDIT) that had actual expected
    Sale/Expense activity that shift - Credit is excluded because it was
    never part of the old cash/upi/card reconciliation either (it's
    never collected at the point of sale, tracked separately via
    CreditService). A tender with zero expected activity that shift
    gets no line at all, so a typical shift today still produces the
    same ~3 lines the old columns did (Cash, Card, Other - UPI sales
    map to Other, see Tender's own docstring) without any schema change
    needed once the app starts attributing sales to specific tenders
    like DTP Card/PhonePe/Paytm.

    One row per (shift_reconciliation, tender) - the unique constraint
    is what makes "one line per tender" an enforced invariant, not just
    a convention ReconciliationService happens to follow.
    """

    __tablename__ = "shift_reconciliation_lines"

    __table_args__ = (
        UniqueConstraint(
            "shift_reconciliation_id", "tender_id", name="uq_shift_reconciliation_lines_recon_tender"
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_reconciliation_id = Column(
        String(36), ForeignKey("shift_reconciliations.id"), nullable=False, index=True
    )
    tender_id = Column(String(36), ForeignKey("tenders.id"), nullable=False, index=True)

    expected = Column(Numeric(12, 2), nullable=False)
    declared = Column(Numeric(12, 2), nullable=False)
    variance = Column(Numeric(12, 2), nullable=False)

    shift_reconciliation = relationship("ShiftReconciliation", back_populates="lines")
    tender = relationship("Tender")

    def __repr__(self) -> str:
        return f"<ShiftReconciliationLine(tender_id={self.tender_id!r}, variance={self.variance!r})>"
