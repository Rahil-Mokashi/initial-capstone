"""The owner's daily digest: one page that says how the day went and what needs a decision (LAN build, Phase 5).

Nothing here is computed again: every figure comes from the service that already owns it (the daily report for the shifts, the checks
engine, the review chain, the credit ageing, the expenses). The shortage or excess per shift uses the SAME formula and tolerance as
the Close Shift desk (`tally_status`). Each owner marks a day "reviewed" for themselves; the first mark is kept.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission
from app.core.money import money
from app.core.permissions import require_permission
from app.models.digest_review import DigestReview
from app.models.shift import Shift
from app.models.shift_entry import ShiftEntry
from app.services.close_desk_service import tally_status

_Z = Decimal("0")


@dataclass
class DigestShift:
    shift_id: str
    label: str
    total_sale: Decimal
    collected: Decimal
    difference: Decimal
    status: str  # balanced | short | excess
    entry_status: Optional[str]


@dataclass
class DigestCheck:
    sentence: str
    status: str


@dataclass
class Digest:
    day: date
    shifts: List[DigestShift]
    total_sale: Decimal
    litres_sold: Decimal
    credit_sales: Decimal
    credit_outstanding: Decimal
    checks_total: int
    checks_passed: int
    checks_to_look_at: List[DigestCheck]
    waiting: dict  # entry status -> number of the day's shifts standing there
    pending_expenses: int
    reviewed: List[tuple] = field(default_factory=list)  # (username, reviewed_at)
    reviewed_by_me: bool = False


class DigestService:
    def __init__(self, session, report_service, check_service, workflow, ledger, audit_repo, auth_service):
        self._session = session
        self._audit_repo = audit_repo
        self._report = report_service
        self._checks = check_service
        self._workflow = workflow
        self._ledger = ledger
        self._auth_service = auth_service

    @require_permission(Permission.DIGEST_VIEW.value)
    def default_day(self, actor_user_id: str) -> date:
        """The latest day that has any shift, otherwise today."""
        latest = self._session.query(Shift.shift_date).order_by(Shift.shift_date.desc()).first()
        return latest[0] if latest else date.today()

    @require_permission(Permission.DIGEST_VIEW.value)
    def build(self, actor_user_id: str, day: date) -> Digest:
        report = self._report.compute(day, actor_user_id)
        entries = {e.shift_id: e.status for e in self._session.query(ShiftEntry).all()}
        shifts, litres = [], _Z
        for block in report.shifts:
            if not block.shift_id:
                continue
            diff, status = tally_status(block)
            real = self._session.get(Shift, block.shift_id)
            shifts.append(DigestShift(block.shift_id, real.shift_label if real else block.label, block.total_sale, block.lines_total, diff, status, entries.get(block.shift_id)))
            litres += sum(block.litres_by_tank.values(), _Z) + block.unassigned_litres
        rows = self._checks.results_for_day.__wrapped__(self._checks, actor_user_id, day, None)
        summary = self._checks.summary(rows)
        look = [DigestCheck(r.sentence, r.status) for r in rows if r.status != "pass"][:5]
        reviews = self._session.query(DigestReview).filter_by(day=day).order_by(DigestReview.reviewed_at).all()
        ageing = self._ledger.ageing.__wrapped__(self._ledger, actor_user_id, day)
        return Digest(
            day=day, shifts=shifts, total_sale=money(sum((s.total_sale for s in shifts), _Z)), litres_sold=litres,
            credit_sales=money(sum((b.credit_total for b in report.shifts), _Z)), credit_outstanding=ageing.total_balance,
            checks_total=summary["total"], checks_passed=summary["passed"], checks_to_look_at=look,
            waiting=self._workflow.counts_by_status(day), pending_expenses=sum(b.pending_expenses for b in report.shifts),
            reviewed=[(r.user.username, r.reviewed_at) for r in reviews], reviewed_by_me=any(r.user_id == actor_user_id for r in reviews),
        )

    @require_permission(Permission.DIGEST_VIEW.value)
    def mark_reviewed(self, actor_user_id: str, day: date) -> Digest:
        if not self._session.query(DigestReview).filter_by(day=day, user_id=actor_user_id).first():
            self._session.add(DigestReview(day=day, user_id=actor_user_id))
            self._session.commit()
            self._audit_repo.record(event_type="digest_reviewed", actor_id=actor_user_id, entity_type="Digest", description=f"Digest of {day} marked as reviewed")
        return self.build.__wrapped__(self, actor_user_id, day)
