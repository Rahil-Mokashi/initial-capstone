"""One check in the checks engine about the Main PC itself: is the newest backup recent enough? (LAN build, Phase 7)

"Latest backup is 40 hours old (limit 36)". Only for today (a backup's age is a statement about now). It uses the age the System health
screen shows, and the limit is the owners' Owner Choice `backup_max_age_hours`: up to twice the limit is a warning, beyond that a failure.
"""

from datetime import date
from decimal import Decimal
from typing import List

from app.services.check_service import CheckSpec


class SystemChecks:
    def __init__(self, check_service, health, settings, enabled: bool = True):
        self._enabled = enabled  # only a Main PC watches its own backups; a Single PC's backups are the Qt app's concern
        self._checks = check_service
        self._health = health
        self._settings = settings

    def run_day(self, actor_id, day: date) -> list:
        return [self._checks.record(actor_id, s) for s in self.specs_for_day(day)]

    def specs_for_day(self, day: date) -> List[CheckSpec]:
        if not self._enabled or day != date.today():
            return []
        limit = Decimal(self._settings.get("backup_max_age_hours"))
        age = self._health.backup_age_hours()
        if age is None:
            actual, sentence = limit * 3, "No backup has been taken yet"
        else:
            actual, sentence = Decimal(str(round(age, 1))), f"Latest backup is {age:.0f} hours old (limit {limit:.0f})"
        return [CheckSpec(
            key="system.backup_is_recent", scope_type="day", scope_id=day.isoformat(), business_date=day, area="System", unit="count",
            sentence=sentence, expected=limit, actual=actual, rule="at_most", warn_within=limit,
            links=[{"label": "Open System health", "route": "/system-health"}],
        )]
