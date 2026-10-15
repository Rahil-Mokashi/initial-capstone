"""The mail sender's own thread (Main PC only). Wakes every minute; does nothing at all while mail is off.

It owns its database session and never touches a request: whatever it does or however long the mail server takes, no screen waits for it.
"""

import threading
from datetime import date, datetime
from typing import Callable

from app.core.logging import logger


class MailScheduler:
    def __init__(self, make_services: Callable, interval_seconds: float = 60.0, now: Callable[[], datetime] = datetime.now):
        """`make_services()` returns (services, close) with a fresh Services container and a function that closes its session."""
        self._make = make_services
        self._interval = interval_seconds
        self._now = now
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="mail-sender", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(5)

    def tick(self) -> None:
        """One pass: queue today's summary when it is due, then send what is pending. Errors are logged, never raised."""
        services, close = self._make()
        try:
            mail = services.mail
            if not mail.enabled():
                return
            hour = int(services.pump_settings.get("mail_send_hour"))
            now = self._now()
            if now.hour >= hour:
                owner = services.digest_owner_id()
                if owner:
                    mail.enqueue_daily_summary(services.digest.build.__wrapped__(services.digest, owner, now.date()))
            mail.send_due()
        except Exception as exc:  # noqa: BLE001
            logger.error("Mail sender pass failed: %s", exc, exc_info=exc)
        finally:
            close()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self.tick()
