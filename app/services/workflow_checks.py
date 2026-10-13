"""One check about the review chain: entries that nobody has verified yet (LAN build, Phase 4).

"Day 13 Oct: 2 entries not yet verified". It only warns (it is a reminder to the accountant, not a verdict on the figures), and it
is silent for a day with no entries at all.
"""

from datetime import date
from decimal import Decimal
from typing import List

from app.models.shift_entry import ENTERED
from app.services.check_service import CheckSpec

_Z = Decimal("0")


class WorkflowChecks:
    def __init__(self, check_service, workflow):
        self._checks = check_service
        self._workflow = workflow

    def run_day(self, actor_id, day: date) -> list:
        return [self._checks.record(actor_id, s) for s in self.specs_for_day(day)]

    def specs_for_day(self, day: date) -> List[CheckSpec]:
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
