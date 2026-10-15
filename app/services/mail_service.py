"""The owners' daily summary by email: optional, OFF by default, outbound only, read-only (LAN build, Phase 6).

Nothing connects in from the internet; this is the only code in the application that ever connects OUT, and only when an owner has turned
it on and filled in a mail server. The message is the day's figures (sale, litres, per-shift verdict, checks, what is waiting): no
customer or employee names, no bank details, nothing an outsider could use. The mail password is never kept in the database or in a
setting: the caller supplies it from the DPAPI-protected secret file when a message is sent.

Sending happens in the sender's own thread (api/lan/mail_scheduler.py) from the outbox, never inside a request, so a mail server that is
down, slow or wrong can never delay or break anything else. Every outcome is audit-logged.
"""

import smtplib
import ssl
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage
from typing import Callable, List, Optional

from app.core.constants import Permission
from app.core.logging import logger
from app.core.permissions import require_permission
from app.models.mail_outbox import MailOutbox

RETRY_AFTER = timedelta(minutes=15)
GIVE_UP_AFTER = 6
SMTP_SECONDS = 20
LOOPBACK = ("127.0.0.1", "localhost")


class MailNotReady(Exception):
    """Mail is off or not filled in; the message says what is missing."""


def split_addresses(text: str) -> List[str]:
    return [a.strip() for a in (text or "").replace(";", ",").split(",") if a.strip()]


def summary_text(digest) -> tuple:
    """(subject, body) from a Digest: figures only."""
    lines = [
        f"Petrol pump daily summary for {digest.day:%d %b %Y}",
        "",
        f"Total sale: {digest.total_sale}",
        f"Litres sold: {digest.litres_sold}",
        f"Credit sales: {digest.credit_sales}",
        f"Credit outstanding: {digest.credit_outstanding}",
        "",
    ]
    for s in digest.shifts:
        verdict = {"balanced": "balanced", "short": f"SHORT {s.difference}", "excess": f"excess {str(s.difference).lstrip('-')}"}[s.status]
        lines.append(f"{s.label}: sold {s.total_sale}, collected {s.collected}, {verdict}")
    lines += ["", f"Checks passed: {digest.checks_passed} of {digest.checks_total}"]
    for c in digest.checks_to_look_at:
        lines.append(f"  - {c.sentence}")
    waiting = {k: v for k, v in digest.waiting.items() if k != "locked"}
    if waiting or digest.pending_expenses:
        lines.append("")
        lines.append("Waiting for a decision: " + ", ".join(f"{n} {k}" for k, n in waiting.items()) + (f", {digest.pending_expenses} expenses not approved" if digest.pending_expenses else ""))
    lines += ["", "This message was sent by your pump's Main PC. It contains figures only. Open the app for details."]
    shorts = sum(1 for s in digest.shifts if s.status == "short")
    subject = f"Pump summary {digest.day:%d %b}: {digest.total_sale} sold" + (f", {shorts} shift(s) short" if shorts else "")
    return subject, "\n".join(lines)


class MailService:
    def __init__(self, session, settings, audit_repo, auth_service, password_provider: Callable[[], Optional[str]] = lambda: None,
                 smtp_factory: Optional[Callable] = None):
        self._session = session
        self._settings = settings
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._password = password_provider
        self._smtp_factory = smtp_factory or self._connect

    # ---- configuration
    def enabled(self) -> bool:
        return self._settings.get("mail_enabled") == "on"

    def problems(self) -> List[str]:
        """What is missing before a message could be sent (empty = ready)."""
        out = []
        for key, what in (("mail_host", "the mail server"), ("mail_from", "the sender address"), ("mail_to", "who it goes to")):
            if not self._settings.get(key).strip():
                out.append(f"Fill in {what}.")
        if self._settings.get("mail_user").strip() and not self._password():
            out.append("Type the mail password.")
        if self._settings.get("mail_security") == "none" and self._settings.get("mail_host").strip() not in LOOPBACK:
            out.append("Sending without encryption is only allowed to this PC itself.")
        return out

    # ---- queue
    def enqueue_daily_summary(self, digest) -> Optional[MailOutbox]:
        """Queue the day's summary once. Off, not filled in, or already queued: nothing happens (returns None)."""
        if not self.enabled() or self.problems():
            return None
        if self._session.query(MailOutbox).filter_by(kind="daily_summary", day=digest.day).first():
            return None
        subject, body = summary_text(digest)
        row = MailOutbox(kind="daily_summary", day=digest.day, to_addrs=", ".join(split_addresses(self._settings.get("mail_to"))), subject=subject, body=body)
        self._session.add(row)
        self._session.commit()
        return row

    def send_due(self, now: Optional[datetime] = None) -> int:
        """Try every pending message that is due. Never raises. Returns how many were sent."""
        now = now or datetime.now(timezone.utc)
        sent = 0
        rows = self._session.query(MailOutbox).filter(MailOutbox.status == "pending").order_by(MailOutbox.created_at).all()
        for row in rows:
            due = row.next_try_at
            if due is not None and (due.replace(tzinfo=timezone.utc) if due.tzinfo is None else due) > now:
                continue
            sent += 1 if self._attempt(row, now) else 0
        return sent

    def _attempt(self, row: MailOutbox, now: datetime) -> bool:
        row.attempts += 1
        try:
            self._deliver(row.to_addrs, row.subject, row.body)
        except Exception as exc:  # noqa: BLE001 - whatever went wrong, record it and carry on
            row.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            row.status = "gave_up" if row.attempts >= GIVE_UP_AFTER else "pending"
            row.next_try_at = now + RETRY_AFTER
            logger.warning("Daily summary mail could not be sent (attempt %s): %s", row.attempts, row.last_error)
            self._session.commit()
            self._audit_repo.record(event_type="mail_failed", description=f"Daily summary for {row.day} not sent (attempt {row.attempts}): {row.last_error}")
            return False
        row.status, row.sent_at, row.last_error = "sent", now, None
        self._session.commit()
        self._audit_repo.record(event_type="mail_sent", description=f"Daily summary for {row.day} sent to {row.to_addrs}")
        return True

    # ---- the one place that talks to a mail server
    @require_permission(Permission.MAIL_MANAGE.value)
    def send_test(self, actor_user_id: str) -> str:
        """Send a short test message now and say what happened (for the owner pressing 'Send a test')."""
        missing = self.problems()
        if missing:
            raise MailNotReady(" ".join(missing))
        try:
            self._deliver(", ".join(split_addresses(self._settings.get("mail_to"))), "Test message from your petrol pump",
                          "If you can read this, the daily summary email is set up correctly.\nNo figures are in this message.")
        except Exception as exc:  # noqa: BLE001
            self._audit_repo.record(event_type="mail_test_failed", actor_id=actor_user_id, description=f"Test mail failed: {type(exc).__name__}")
            raise MailNotReady(f"The mail server did not accept the message: {type(exc).__name__}: {str(exc)[:160]}") from exc
        self._audit_repo.record(event_type="mail_test_sent", actor_id=actor_user_id, description="Test mail sent")
        return "The test message was sent."

    def _deliver(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self._settings.get("mail_from").strip(), to, subject
        message.set_content(body)
        server = self._smtp_factory()
        try:
            user = self._settings.get("mail_user").strip()
            if user:
                server.login(user, self._password() or "")
            server.send_message(message)
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass

    def _connect(self):
        host, port = self._settings.get("mail_host").strip(), int(self._settings.get("mail_port"))
        security = self._settings.get("mail_security")
        context = ssl.create_default_context()  # certificates are always checked
        if security == "ssl":
            return smtplib.SMTP_SSL(host, port, timeout=SMTP_SECONDS, context=context)
        server = smtplib.SMTP(host, port, timeout=SMTP_SECONDS)
        if security == "starttls":
            server.starttls(context=context)
        return server

    # ---- for the owner's screen
    @require_permission(Permission.MAIL_MANAGE.value)
    def status(self, actor_user_id: str) -> dict:
        rows = self._session.query(MailOutbox).order_by(MailOutbox.created_at.desc()).limit(10).all()
        last_ok = next((r for r in rows if r.status == "sent"), None)
        return {
            "enabled": self.enabled(), "problems": self.problems(), "password_set": bool(self._password()),
            "pending": sum(1 for r in rows if r.status == "pending"), "last_sent": last_ok.sent_at if last_ok else None,
            "outbox": rows,
        }
