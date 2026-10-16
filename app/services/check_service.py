"""The checks engine: named verifications the owners can SEE pass or fail.

`evaluate` is the pure rule (numbers in, verdict out). `CheckService.record`
stores a verdict append-only: if the newest stored result for the same
(check, scope) says exactly the same thing nothing is written, otherwise a
NEW row supersedes it and an audit event is written. Nothing here updates or
deletes a result, and `explain` only attaches a note (who, when) - it can
never change a status, so a failure cannot be turned into a pass by a person.
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.models.check_result import CheckExplanation, CheckResult
from app.repositories.base import unit_of_work

PASS, WARN, FAIL = "pass", "warn", "fail"
SCOPES = ("day", "shift", "tank", "bill", "customer", "bank_account", "payroll_month")
AREAS = ("Daily report", "Cash", "Stock", "Credit", "Bank", "Payroll")
_ZERO = Decimal("0")


@dataclass
class CheckSpec:
    """What a runner hands to the engine."""

    key: str
    scope_type: str
    scope_id: str
    business_date: date
    area: str
    sentence: str
    expected: Optional[Decimal]
    actual: Optional[Decimal]
    unit: str = "rs"
    # |difference| up to warn_within is a warning, anything above is a failure. 0 = exact.
    warn_within: Decimal = _ZERO
    # Differences up to pass_within count as a pass (e.g. a half-paisa rounding).
    pass_within: Decimal = _ZERO
    links: List[dict] = field(default_factory=list)
    # "equal": actual must equal expected. "at_most": actual must not exceed expected (a limit).
    # "at_least": actual must not fall below expected (a floor, e.g. cash in hand never below zero).
    rule: str = "equal"


def evaluate(spec: CheckSpec) -> str:
    """pass / warn / fail from the two numbers. A missing side is a failure, never a pass."""
    if spec.expected is None or spec.actual is None:
        return FAIL
    if spec.rule == "at_most":
        over = spec.actual - spec.expected
        return PASS if over <= spec.pass_within else (WARN if over <= spec.warn_within else FAIL)
    if spec.rule == "at_least":
        short = spec.expected - spec.actual
        return PASS if short <= spec.pass_within else (WARN if short <= spec.warn_within else FAIL)
    gap = abs(spec.actual - spec.expected)
    if gap <= spec.pass_within:
        return PASS
    if gap <= spec.warn_within:
        return WARN
    return FAIL


class CheckService:
    def __init__(self, result_repo, explanation_repo, audit_repo, auth_service):
        self._results = result_repo
        self._explanations = explanation_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    # -- writing (engine-internal: runners call this on behalf of whoever just saved data) -------------
    @contextmanager
    def batch(self):
        """Collect the verdicts of one run and write them together in ONE transaction (one commit instead of two per check).

        Inside the block `record` still compares against the stored verdict and returns it when nothing changed; a changed
        verdict is returned as an unsaved row and saved, with its audit entry, when the block ends.
        """
        self._pending = []
        try:
            yield
        finally:
            pending, self._pending = self._pending, None
            with unit_of_work(self._results.session):
                for actor_user_id, spec in pending:
                    self.record(actor_user_id, spec)

    _pending = None

    def record(self, actor_user_id: Optional[str], spec: CheckSpec) -> CheckResult:
        if spec.scope_type not in SCOPES:
            raise ValueError(f"Unknown check scope: {spec.scope_type}")
        status = evaluate(spec)
        difference = (
            spec.actual - spec.expected if spec.expected is not None and spec.actual is not None else None
        )
        links = json.dumps(spec.links, separators=(",", ":"))
        latest = self._results.latest(spec.key, spec.scope_type, spec.scope_id)
        if (
            latest is not None
            and latest.status == status
            and latest.expected == spec.expected
            and latest.actual == spec.actual
            and latest.sentence == spec.sentence
            and latest.links == links
        ):
            return latest
        if self._pending is not None:
            self._pending.append((actor_user_id, spec))
            return CheckResult(
                check_key=spec.key, scope_type=spec.scope_type, scope_id=spec.scope_id,
                business_date=spec.business_date, area=spec.area, sentence=spec.sentence,
                expected=spec.expected, actual=spec.actual, difference=difference, unit=spec.unit,
                status=status, links=links, run_by_id=actor_user_id,
            )
        result = self._results.add(CheckResult(
            check_key=spec.key, scope_type=spec.scope_type, scope_id=spec.scope_id,
            business_date=spec.business_date, area=spec.area, sentence=spec.sentence,
            expected=spec.expected, actual=spec.actual, difference=difference, unit=spec.unit,
            status=status, links=links, run_by_id=actor_user_id,
        ))
        self._audit_repo.record(
            event_type="check_recorded", actor_id=actor_user_id, entity_type="CheckResult",
            entity_id=result.id,
            description=f"{status.upper()}: {spec.sentence} (expected {spec.expected}, actual {spec.actual})",
            old_value=latest.status if latest else None, new_value=status,
        )
        return result

    @require_permission(Permission.CHECK_EXPLAIN.value)
    def explain(self, actor_user_id: str, result_id: str, text: str) -> CheckExplanation:
        text = (text or "").strip()
        if not text:
            raise ValueError("Write what explains this result")
        result = self._results.get_by_id(result_id)
        if result is None:
            raise NotFoundError(f"Check result not found: {result_id}")
        note = self._explanations.add(CheckExplanation(check_result_id=result_id, text=text, created_by_id=actor_user_id))
        self._audit_repo.record(
            event_type="check_explained", actor_id=actor_user_id, entity_type="CheckResult",
            entity_id=result_id, description=f"Explanation added to '{result.sentence}': {text}",
        )
        return note

    # -- reading ----------------------------------------------------------------------------------------
    @require_permission(Permission.CHECK_VIEW.value)
    def results_for_day(self, actor_user_id: str, day: date, area: Optional[str] = None) -> List[CheckResult]:
        """Current results, failures first, then warnings, then passes."""
        rank = {FAIL: 0, WARN: 1, PASS: 2}
        rows = self._results.current_for_day(day, area)
        return sorted(rows, key=lambda r: (rank.get(r.status, 3), r.area, r.sentence))

    @require_permission(Permission.CHECK_VIEW.value)
    def history_for_day(self, actor_user_id: str, day: date) -> List[CheckResult]:
        return self._results.history_for_day(day)

    @require_permission(Permission.CHECK_VIEW.value)
    def get_result(self, actor_user_id: str, result_id: str) -> CheckResult:
        result = self._results.get_by_id(result_id)
        if result is None:
            raise NotFoundError(f"Check result not found: {result_id}")
        return result

    @require_permission(Permission.CHECK_VIEW.value)
    def recent_days(self, actor_user_id: str) -> List[date]:
        return self._results.days_with_results()

    @staticmethod
    def summary(rows: List[CheckResult]) -> dict:
        counts = {PASS: 0, WARN: 0, FAIL: 0}
        for r in rows:
            counts[r.status] = counts.get(r.status, 0) + 1
        return {"total": len(rows), "passed": counts[PASS], "warned": counts[WARN], "failed": counts[FAIL]}
