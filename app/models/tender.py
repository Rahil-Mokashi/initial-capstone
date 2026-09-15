import uuid

from sqlalchemy import Column, String

from .base import Base, EntityMixin


class Tender(EntityMixin, Base):
    """Seeded master data for how a sale/shift-settlement line was paid
    (docs/daily-report-spec.md section 3's per-shift transaction
    breakdown). Deliberately NOT more PaymentMethod (app/core/constants.py)
    enum members: the reference report already proved 4 was wrong (Cash/
    UPI/Card/Credit) and nothing says 8 is final either - DTP Card and a
    plain Card terminal are already two separate rows despite both being
    bank-settled, and a real pump could add a new payment app tomorrow.
    A new tender from here on is a seeded row, like ExpenseCategory or
    Fuel, never a migration to a hardcoded enum. Never deleted, only
    deactivated (EntityMixin.status) - historical sales/payments must
    keep referencing whichever tender they were recorded against.

    settlement_type (TenderSettlementType in app/core/constants.py)
    drives reconciliation behaviour without hardcoding a specific
    tender's name into that logic: IMMEDIATE_CASH clears into the till
    the moment the sale happens, BANK_SETTLED clears a few days later via
    a bank statement (a card network, a UPI app), INVOICED_CREDIT is
    never collected at the point of sale at all (a customer's running
    account, collected later via CreditService). This is what makes
    PROJECT_CONTEXT.md's A3 assumption (is DTP Card really a separate
    settlement scheme from a plain card terminal, or the same one
    entered differently?) a one-row change if the owner answers
    differently - update this row's settlement_type, not any code.
    """

    __tablename__ = "tenders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    settlement_type = Column(String(32), nullable=False)

    def __repr__(self) -> str:
        return f"<Tender(name={self.name!r}, settlement_type={self.settlement_type!r}, status={self.status!r})>"
