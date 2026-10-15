"""The Main PC's own backup and safety-check thread. It calls the existing backup code; it never changes it.

Every minute it asks the existing rule whether a backup is due and takes one if so. Once a night (after `nightly_check_hour`) it also
checks the database file, verifies the audit chain and copies the newest backup to the off-device folder if one is set up. Each outcome
is recorded (HealthRun) and shows on the System health screen; a failure is audit-logged. Errors are logged, never raised.
"""

import threading
from datetime import datetime
from typing import Callable

from app.core.logging import logger
from app.models.health_run import HealthRun


class BackupScheduler:
    def __init__(self, make_services: Callable, interval_seconds: float = 60.0, now: Callable[[], datetime] = datetime.now):
        """`make_services()` returns (services, close): a fresh Services container and the function that closes its session."""
        self._make = make_services
        self._interval = interval_seconds
        self._now = now
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="backup-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(5)

    def tick(self) -> None:
        services, close = self._make()
        try:
            health = services.system_health
            now = self._now()
            hour = int(services.pump_settings.get("nightly_check_hour"))
            done_today = (
                services.db.query(HealthRun).filter(HealthRun.kind == "integrity").order_by(HealthRun.at.desc()).first()
            )
            ran_today = done_today is not None and done_today.at.astimezone().date() == now.date()
            if now.hour >= hour and not ran_today:
                health.run_all()
            else:
                health.run_backup_if_due()
        except Exception as exc:  # noqa: BLE001
            logger.error("Backup scheduler pass failed: %s", exc, exc_info=exc)
        finally:
            close()

    def _run(self) -> None:
        self.tick()  # at start: a Main PC that was off over the night catches up at once
        while not self._stop.wait(self._interval):
            self.tick()
