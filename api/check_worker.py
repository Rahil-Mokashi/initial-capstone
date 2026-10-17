"""Runs the automatic checks in the background so a save returns at once.

One worker thread per app. Writes call `request_run`; bursts of saves are merged (a short quiet period), then the
checks run once for the days that need them. The verdicts are the same append-only, audit-logged rows as before,
they just appear a moment after the save instead of before the reply. Errors are logged and never reach the user.
"""

import threading
import time

from api.services import Services
from app.core.logging import logger

QUIET_SECONDS = 0.5  # wait this long after the last save before running, so a burst of saves costs one run
INLINE = False  # tests set this: run inside the save so a test can read the verdicts straight after it


class CheckWorker:
    def __init__(self, session_factory, session_timeout_hours):
        self._session_factory = session_factory
        self._timeout_hours = session_timeout_hours
        self._cond = threading.Condition()
        self._token = None  # newest session token that asked for a run; None = nothing pending
        self._due = 0.0
        self._running = False
        threading.Thread(target=self._loop, name="check-worker", daemon=True).start()

    def request(self, token: str) -> None:
        with self._cond:
            self._token = token
            self._due = time.monotonic() + QUIET_SECONDS
            self._cond.notify_all()

    def busy(self) -> bool:
        with self._cond:
            return self._token is not None or self._running

    def wait_idle(self, timeout: float = 60.0) -> bool:
        end = time.monotonic() + timeout
        with self._cond:
            while self._token is not None or self._running:
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(min(left, 0.1))
        return True

    def _loop(self) -> None:
        while True:
            with self._cond:
                while self._token is None or time.monotonic() < self._due:
                    self._cond.wait(max(self._due - time.monotonic(), 0.05) if self._token else None)
                token, self._token, self._running = self._token, None, True
            try:
                run_checks(self._session_factory, self._timeout_hours, token)
            finally:
                with self._cond:
                    self._running = False
                    self._cond.notify_all()


def run_checks(session_factory, timeout_hours, token: str) -> None:
    db = session_factory()
    try:
        services = Services(db, timeout_hours)
        user = services.auth.validate_session(token)
        if user is None:
            return
        for day in services.days_to_check():
            with services.checks.batch():
                services.run_all_checks(user.id, day)
    except Exception as exc:  # a verification problem must never break the save that triggered it
        logger.error("Automatic checks failed: %s", exc, exc_info=exc)
        db.rollback()
    finally:
        db.close()


def request_run(app, token: str) -> None:
    if INLINE:
        run_checks(app.state.session_factory, app.state.session_timeout_hours, token)
        return
    worker = getattr(app.state, "check_worker", None)
    if worker is None:
        worker = app.state.check_worker = CheckWorker(app.state.session_factory, app.state.session_timeout_hours)
    worker.request(token)


def wait_idle(app, timeout: float = 60.0) -> bool:
    worker = getattr(app.state, "check_worker", None)
    return True if worker is None else worker.wait_idle(timeout)


def is_updating(app) -> bool:
    worker = getattr(app.state, "check_worker", None)
    return worker is not None and worker.busy()
