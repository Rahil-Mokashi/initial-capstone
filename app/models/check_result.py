"""Checks engine storage (site visit 2026-10-12: "the owners want to SEE every verification").

A CheckResult is one verification outcome: what was compared, the two
numbers, and the verdict. Rows are append-only - a re-run that changes
the outcome inserts a NEW row and the newest row for a (check_key, scope)
is the current one; nothing is ever updated or deleted, so a failure
that later "fixes itself" stays visible in the history. A CheckExplanation
is a person's note on a result: it records who/when and never changes the
status.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (Index("ix_check_results_latest", "check_key", "scope_type", "scope_id", "run_at"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Stable name of the rule, e.g. "shift.tenders_add_up". With scope_type/scope_id it
    # identifies "the same check on the same thing" across re-runs.
    check_key = Column(String(96), nullable=False, index=True)
    # day | shift | tank | bill | customer | bank_account | payroll_month
    scope_type = Column(String(24), nullable=False)
    scope_id = Column(String(64), nullable=False)
    business_date = Column(Date, nullable=False, index=True)
    area = Column(String(32), nullable=False, index=True)
    sentence = Column(String(400), nullable=False)
    expected = Column(Numeric(16, 3), nullable=True)
    actual = Column(Numeric(16, 3), nullable=True)
    difference = Column(Numeric(16, 3), nullable=True)
    unit = Column(String(12), nullable=False, default="rs")  # rs | litres | count
    status = Column(String(8), nullable=False, index=True)  # pass | warn | fail
    # JSON list of {"label": str, "route": str}: the records behind the numbers.
    links = Column(Text, nullable=False, default="[]")
    run_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    run_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    explanations = relationship("CheckExplanation", back_populates="result", order_by="CheckExplanation.created_at")

    def __repr__(self) -> str:
        return f"<CheckResult({self.check_key!r}, {self.scope_type}:{self.scope_id}, {self.status})>"


class CheckExplanation(Base):
    __tablename__ = "check_explanations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    check_result_id = Column(String(36), ForeignKey("check_results.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    result = relationship("CheckResult", back_populates="explanations")
    created_by = relationship("User")
