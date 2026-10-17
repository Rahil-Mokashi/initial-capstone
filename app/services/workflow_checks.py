"""One check about the review chain: entries that nobody has verified yet (LAN build, Phase 4).

"Day 13 Oct: 2 entries not yet verified". It only warns (it is a reminder to the accountant, not a verdict on the figures), and it
is silent for a day with no entries at all.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List

from app.core.constants import ShiftStatus
from app.models.shift import Shift
from app.models.shift_entry import ENTERED
from app.services.check_service import CheckSpec

_Z = Decimal("0")


class WorkflowChecks:
    def __init__(self, check_service, workflow, session=None):
        self._checks = check_service
        self._workflow = workflow
        self._session = session

    def run_day(self, actor_id, day: date) -> list:
        return [self._checks.record(actor_id, s) for s in self.specs_for_day(day)]

    def specs_for_day(self, day: date) -> List[CheckSpec]:
        return self._open_too_long(day) + self._entries_verified(day)

    def _open_too_long(self, day: date) -> List[CheckSpec]:
        """A shift left open for more than 24 hours: it blocks the day's figures and slows every check. A statement about now, so only for today."""
        if self._session is None or day != date.today():
            return []
        limit = datetime.now(timezone.utc) - timedelta(hours=24)
        stale = [
            s for s in self._session.query(Shift).filter(Shift.status == ShiftStatus.OPEN.value).all()
            if (s.start_time or s.created_at) < limit
        ]
        names = ", ".join(f"{s.shift_date.day} {s.shift_date.strftime('%b')} {s.shift_label}" for s in stale)
        return [CheckSpec(
            key="shift.open_too_long", scope_type="day", scope_id=day.isoformat(), business_date=day, area="Shifts", unit="count",
            sentence=f"{len(stale)} shift(s) open for more than 24 hours: {names}" if stale else "No shift has been open for more than 24 hours",
            expected=_Z, actual=Decimal(len(stale)), warn_within=_Z,
            links=[{"label": "Open Shifts", "route": "/shifts"}],
        )]

    def _entries_verified(self, day: date) -> List[CheckSpec]:
        counts = self._workflow.counts_by_status(day)
        if not counts:
            return []
        waiting = counts.get(ENTERED, 0)
        word = "entry" if waiting == 1 else "entries"
        return [
            CheckSpec(
                key="workflow.entries_verified", scope_type="day", scope_id=day.isoformat(), business_date=day, area="Review",
                sentence=f"Day {day.day} {day.strftime('%b')}: {waiting} {word} not yet verified" if waiting else f"Day {day.day} {day.strftime('%b')}: every entry has been verified",
                expected=_Z, actual=Decimal(waiting), unit="count", warn_within=Decimal("1000"),
                links=[{"label": "Open Review", "route": "/review"}],
            )
        ]
