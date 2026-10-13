"""Bank statement reconciliation (site visit 2026-10-12): the owners' biggest pain is checking bulk bank credits
against the books by hand.

Design rules, same as the rest of the app: statement rows are IMMUTABLE once imported (a correction is a new
import, a mistaken match is voided not deleted), every match records who made it and why, and nothing is
ever forced: a bank line that cannot be tied to the pump stays "not ours" or unmatched. The goodwill
business that shares the office is out of scope, so its credits simply stay unmatched or are marked not ours.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base, EntityMixin


class BankAccount(EntityMixin, Base):
    __tablename__ = "bank_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_mask = Column(String(32), nullable=True)  # e.g. XXXX1234: never the full number
    notes = Column(Text, nullable=True)

    modes = relationship("BankAccountMode", back_populates="account", cascade="all, delete-orphan")


class BankAccountMode(Base):
    """Which payment modes settle into an account (H-02): a setting per account, because the owner has not said."""

    __tablename__ = "bank_account_modes"
    __table_args__ = (UniqueConstraint("bank_account_id", "mode", name="uq_bank_account_modes"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    # A tender name (Paytm, PhonePe, DTP Card, Card, Other) or cash_deposit / credit_receipts / payroll
    mode = Column(String(32), nullable=False)

    account = relationship("BankAccount", back_populates="modes")


class BankImportProfile(Base):
    """A saved column mapping for one bank's file layout."""

    __tablename__ = "bank_import_profiles"
    __table_args__ = (UniqueConstraint("bank_account_id", "name", name="uq_bank_import_profiles"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    mapping_json = Column(Text, nullable=False)
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class BankStatementImport(Base):
    __tablename__ = "bank_statement_imports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_sha256 = Column(String(64), nullable=False)
    imported_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    imported_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    row_count = Column(Integer, nullable=False)
    new_rows = Column(Integer, nullable=False)
    duplicate_rows = Column(Integer, nullable=False)
    date_from = Column(Date, nullable=True)
    date_to = Column(Date, nullable=True)
    opening_balance = Column(Numeric(14, 2), nullable=True)
    closing_balance = Column(Numeric(14, 2), nullable=True)
    continuity_ok = Column(Boolean, nullable=False, default=True)
    break_count = Column(Integer, nullable=False, default=0)
    continuity_notes = Column(Text, nullable=True)

    account = relationship("BankAccount")


class BankStatementRow(Base):
    """One line of a bank statement, exactly as imported. Never edited, never deleted."""

    __tablename__ = "bank_statement_rows"
    __table_args__ = (UniqueConstraint("bank_account_id", "row_hash", name="uq_bank_statement_rows_hash"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_id = Column(String(36), ForeignKey("bank_statement_imports.id"), nullable=False, index=True)
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False)
    txn_date = Column(Date, nullable=False, index=True)
    description = Column(Text, nullable=False)
    reference = Column(String(64), nullable=True, index=True)
    debit = Column(Numeric(14, 2), nullable=False, default=0)
    credit = Column(Numeric(14, 2), nullable=False, default=0)
    balance = Column(Numeric(14, 2), nullable=True)
    row_hash = Column(String(64), nullable=False)
    raw_json = Column(Text, nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    account = relationship("BankAccount")


class ExpectedReceipt(Base):
    """Money the books say should reach (or leave) the bank. Derived from the app's own records and refreshed on sync."""

    __tablename__ = "expected_receipts"
    __table_args__ = (
        CheckConstraint("direction IN ('credit','debit')", name="ck_expected_receipts_direction"),
        CheckConstraint("status IN ('active','void')", name="ck_expected_receipts_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_key = Column(String(128), nullable=False, unique=True)  # e.g. shift_mode:<shift>:<tender>
    source_type = Column(String(24), nullable=False)  # shift_mode | cash_deposit | credit_payment | payroll
    source_id = Column(String(64), nullable=False)
    direction = Column(String(8), nullable=False, default="credit")
    mode = Column(String(32), nullable=False, index=True)
    business_date = Column(Date, nullable=False, index=True)
    win_from = Column(Date, nullable=False)
    win_to = Column(Date, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    reference = Column(String(128), nullable=True)
    description = Column(String(255), nullable=False)
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=True)
    status = Column(String(8), nullable=False, default="active")
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class BankMatch(Base):
    """A pairing of expected receipts with bank lines (or a bank line marked not ours / a reversal)."""

    __tablename__ = "bank_matches"
    __table_args__ = (
        CheckConstraint("kind IN ('match','not_ours','reversal')", name="ck_bank_matches_kind"),
        CheckConstraint("status IN ('suggested','confirmed','void')", name="ck_bank_matches_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(String(12), nullable=False, default="match")
    status = Column(String(12), nullable=False)
    rule = Column(String(24), nullable=False)  # reference | amount_date | many_to_one | one_to_many | manual | reversal | not_ours
    auto = Column(Boolean, nullable=False, default=False)
    charges = Column(Numeric(14, 2), nullable=False, default=0)  # deducted by the bank before settlement
    note = Column(Text, nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    confirmed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(UtcDateTime, nullable=True)
    locked = Column(Boolean, nullable=False, default=False)  # H-25: an owner can lock a confirmed match
    locked_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    locked_at = Column(UtcDateTime, nullable=True)
    voided_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    voided_at = Column(UtcDateTime, nullable=True)
    void_reason = Column(Text, nullable=True)

    items = relationship("BankMatchItem", back_populates="match", cascade="all, delete-orphan")


class BankMatchItem(Base):
    __tablename__ = "bank_match_items"
    __table_args__ = (
        CheckConstraint("(expected_id IS NULL) != (row_id IS NULL)", name="ck_bank_match_items_one_side"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id = Column(String(36), ForeignKey("bank_matches.id"), nullable=False, index=True)
    expected_id = Column(String(36), ForeignKey("expected_receipts.id"), nullable=True, index=True)
    row_id = Column(String(36), ForeignKey("bank_statement_rows.id"), nullable=True, index=True)

    match = relationship("BankMatch", back_populates="items")
    expected = relationship("ExpectedReceipt")
    row = relationship("BankStatementRow")
