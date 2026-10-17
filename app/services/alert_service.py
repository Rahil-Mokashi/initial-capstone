"""The alert list people can act on: the same alerts as NotificationService, minus the ones set aside, each with a stable key.

* Same alert about the same record on the same day: shown once, with a count.
* Acknowledge (needs a reason; who and when are kept and audit-logged) hides it for the rest of that business day.
* A cash shortage carries the people who worked that shift so one button can book it against one of them ("Mark against <name>");
  booking it resolves the alert, because the shortage is then on that person's account (EmployeeShortageService).
Resolving everything else is automatic: the alert is worked out from live data, so it goes when the problem does.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from app.core.constants import NotificationCategory, Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.alert_acknowledgement import AlertAcknowledgement
from app.repositories.base import unit_of_work
from app.schemas.employee_cash_shortage import EmployeeCashShortageRecord


@dataclass
class ShortageContext:
    line_id: str
    shift_label: str
    employees: List[tuple] = field(default_factory=list)  # (employee_id, name)
    suggested_employee_id: Optional[str] = None  # set when exactly one person worked the shift


@dataclass
class AlertItem:
    key: str
    notification: object
    count: int = 1
    shortage: Optional[ShortageContext] = None


def alert_key(n, day: date) -> str:
    raw = f"{n.category.value}|{n.entity_id or ''}|{n.title}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16] + "@" + day.isoformat()


class AlertService:
    def __init__(self, notifications, ack_repo, shortage_repo, shortages, line_repo, assignment_repo, audit_repo, auth_service):
        self._notifications = notifications
        self._acks = ack_repo
        self._shortage_repo = shortage_repo
        self._shortages = shortages
        self._lines = line_repo
        self._assignments = assignment_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    # ---- reading
    def raw_counts_by_category(self, actor_user_id: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for n in self._notifications.get_notifications(actor_user_id).notifications:
            out[n.category.value] = out.get(n.category.value, 0) + 1
        return out

    def counts_by_category(self, actor_user_id: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for item in self.list(actor_user_id):
            out[item.notification.category.value] = out.get(item.notification.category.value, 0) + 1
        return out

    def list(self, actor_user_id: str, day: Optional[date] = None) -> List[AlertItem]:
        day = day or date.today()
        hidden = self._acks.keys_for_day_suffix("@" + day.isoformat())
        merged: Dict[str, AlertItem] = {}
        order: List[str] = []
        for n in self._notifications.get_notifications(actor_user_id).notifications:
            if n.ref_id and n.category == NotificationCategory.CASH_SHORTAGE and self._shortage_repo.get_by_line_id(n.ref_id):
                continue  # already booked against a person: resolved
            key = alert_key(n, day)
            if key in hidden:
                continue
            if key in merged:
                merged[key].count += 1
                continue
            item = AlertItem(key=key, notification=n)
            if n.category == NotificationCategory.CASH_SHORTAGE and n.ref_id:
                item.shortage = self._shortage_context(n.ref_id)
            merged[key] = item
            order.append(key)
        return [merged[k] for k in order]

    def _shortage_context(self, line_id: str) -> Optional[ShortageContext]:
        line = self._lines.get_by_id(line_id)
        if line is None or line.shift_reconciliation is None or line.shift_reconciliation.shift is None:
            return None
        shift = line.shift_reconciliation.shift
        people: Dict[str, str] = {}
        for a in self._assignments.list_for_shift(shift.id):
            if a.status != "cancelled" and a.employee is not None and a.employee.designation != "Stand-in for shift entry":
                people[a.employee_id] = f"{a.employee.first_name} {a.employee.last_name}".strip()
        ctx = ShortageContext(line_id=line_id, shift_label=f"{shift.shift_date} {shift.shift_label}", employees=sorted(people.items(), key=lambda p: p[1]))
        if len(people) == 1:
            ctx.suggested_employee_id = next(iter(people))
        return ctx

    # ---- acting
    @require_permission(Permission.ALERT_ACKNOWLEDGE.value)
    def acknowledge(self, actor_user_id: str, key: str, reason: str) -> AlertAcknowledgement:
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("Say why this alert can be set aside.")
        item = next((i for i in self.list(actor_user_id) if i.key == key), None)
        if item is None:
            raise NotFoundError("That alert is no longer active.")
        with unit_of_work(self._acks.session):
            row = self._acks.add(AlertAcknowledgement(
                alert_key=key, category=item.notification.category.value, title=item.notification.title[:300],
                reason=reason, acknowledged_by_id=actor_user_id,
            ))
            self._audit_repo.record(
                event_type="alert_acknowledged", actor_id=actor_user_id, entity_type="Alert", entity_id=row.id,
                description=f"{item.notification.title}. Reason: {reason}",
            )
            return row

    def mark_shortage(self, actor_user_id: str, line_id: str, employee_id: str):
        """Book a cash shortage against one of the people who worked that shift (SHORTAGE_MANAGE is checked by the service)."""
        ctx = self._shortage_context(line_id)
        if ctx is None:
            raise NotFoundError("That cash shortage was not found.")
        if employee_id not in {e for e, _ in ctx.employees}:
            raise ConflictError("Choose one of the people who worked that shift.")
        return self._shortages.record_shortage(actor_user_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line_id, employee_id=employee_id))
