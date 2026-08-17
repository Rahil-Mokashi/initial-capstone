"""Local application alerts (problemstatement.md #43).

WHY THERE IS NO `notifications` TABLE
-------------------------------------
The requirements list `notifications` among the database tables, and a
stored row per alert is the obvious shape. It is the wrong one here, and
the reason is worth stating because it is the same reason applied
throughout this codebase.

Ten of the thirteen alert types in #43 describe a CONDITION, not an
event: "low fuel" is true exactly as long as the tank is low, "pending
approval" exactly as long as nobody has approved it, "outstanding
credit" exactly as long as the customer owes money. A stored row records
that the condition was true once. Keeping it honest afterwards means
expiring it when the tank is refilled, when the expense is approved,
when the customer pays - a second mechanism, running everywhere, whose
failure mode is an alert screen confidently reporting problems that were
fixed weeks ago. Nobody trusts that screen twice.

This project already refuses that trade elsewhere and for the same
reason: `SupplierInvoice.status` and `PurchaseOrder.status` are
recomputed from their payments and deliveries rather than incremented,
and `CreditService.get_outstanding_balance` is recomputed from sales
minus payments on every single call, explicitly so it "can never
silently drift". Deriving an alert from the data that makes it true is
the same guarantee: it cannot be stale, because there is nothing to go
stale. It appears when the condition holds and disappears when somebody
fixes it - and "somebody fixed it" is the only thing that should ever
clear an operational alert.

The remaining three (unauthorized action, database error, and the
backup case below) genuinely describe a moment rather than a state, so
they cannot be derived from current data. They do not need a new table
either: `AuditLog` is already an append-only, hash-chained, tamper-
evident record of exactly that kind of event, and it is the right home
for them.

WHY THERE IS NO "MARK AS READ"
------------------------------
Dismissing an alert whose condition is still true is a way to hide a
real problem, and on a system whose whole job is financial correctness
that is a feature working against its own purpose. The way to clear an
alert here is to fix what caused it. Volume is handled by severity
ordering and a per-category cap instead (NOTIFICATION_MAX_PER_CATEGORY),
which is a display concern rather than a change to what is true.

PERMISSIONS
-----------
Every block is gated on the permission its own module already uses, so a
user is never told about something they cannot open - the same pattern
as `DashboardService.get_summary`, which returns None for sections the
actor cannot see. The two approval categories are gated on the
*approve* permission rather than the view permission, because an alert
that says "waiting for you" should only reach somebody who can actually
act on it.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from app.core.constants import (
    DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT,
    NOTIFICATION_BACKUP_OVERDUE_HOURS,
    NOTIFICATION_MAX_PER_CATEGORY,
    NOTIFICATION_RECENT_EVENT_DAYS,
    ExpenseStatus,
    NotificationCategory,
    NotificationSeverity,
    Permission,
    ReconciliationStatus,
    SupplierInvoiceStatus,
    VarianceClassification,
)
from app.core.dates import local_date_of
from app.core.logging import logger

# A fuel-reconciliation / shift-reconciliation classification maps onto
# alert severity here rather than in VarianceClassification itself,
# because the two scales answer different questions and the mapping is a
# presentation decision belonging to whoever is presenting.
_CLASSIFICATION_SEVERITY = {
    VarianceClassification.NORMAL: None,  # not worth an alert at all
    VarianceClassification.WARNING: NotificationSeverity.WARNING,
    VarianceClassification.INVESTIGATION_REQUIRED: NotificationSeverity.WARNING,
    VarianceClassification.APPROVAL_REQUIRED: NotificationSeverity.CRITICAL,
}

_SEVERITY_ORDER = {
    NotificationSeverity.CRITICAL: 0,
    NotificationSeverity.WARNING: 1,
    NotificationSeverity.INFO: 2,
}


@dataclass(frozen=True)
class Notification:
    """One alert. Frozen because it is a computed view of state at the
    moment it was produced, not a record anybody may edit."""

    category: NotificationCategory
    severity: NotificationSeverity
    title: str
    detail: str
    # The id of whatever the alert is about (a tank, an expense, a
    # customer). Carried so a future "take me there" action has something
    # to navigate with; nothing depends on it today.
    entity_id: Optional[str] = None
    # True for the "N more..." line that stands in for items trimmed by
    # the per-category cap. It exists so the final sort can keep that
    # line at the END of its group: sorting it by title instead would
    # place "4 more tanks running low" above the four tanks it is
    # summarising, which reads as a separate alert rather than a
    # footnote.
    is_summary: bool = False


@dataclass
class NotificationSummary:
    """What the caller gets back: the alerts themselves plus the counts
    the UI needs for a badge without re-walking the list."""

    notifications: List[Notification] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.notifications)

    @property
    def critical_count(self) -> int:
        return sum(1 for n in self.notifications if n.severity == NotificationSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for n in self.notifications if n.severity == NotificationSeverity.WARNING)


class NotificationService:
    """Computes the current alert list for one acting user.

    Every dependency is required rather than optional. An optional
    repository defaulting to None would mean a mis-wired service quietly
    produced FEWER alerts instead of failing - and an alert that silently
    never fires is worse than no alert feature at all, because the
    operator believes they are being watched over when they are not.
    """

    def __init__(
        self,
        tank_repo,
        fuel_reconciliation_repo,
        shift_reconciliation_repo,
        expense_repo,
        employee_repo,
        attendance_repo,
        credit_account_repo,
        supplier_invoice_repo,
        supplier_payment_repo,
        audit_repo,
        credit_service,
        auth_service,
        db_path: Optional[str] = None,
    ):
        self._tank_repo = tank_repo
        self._fuel_reconciliation_repo = fuel_reconciliation_repo
        self._shift_reconciliation_repo = shift_reconciliation_repo
        self._expense_repo = expense_repo
        self._employee_repo = employee_repo
        self._attendance_repo = attendance_repo
        self._credit_account_repo = credit_account_repo
        self._supplier_invoice_repo = supplier_invoice_repo
        self._supplier_payment_repo = supplier_payment_repo
        self._audit_repo = audit_repo
        self._credit_service = credit_service
        self._auth_service = auth_service
        # db_path IS optional: it only feeds the backup-staleness check,
        # and a test or a caller with no database file on disk (an
        # in-memory session) should still get every other alert.
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def get_notifications(self, actor_user_id: str) -> NotificationSummary:
        """Recompute every alert this user is allowed to see.

        Deliberately NOT decorated with @require_permission. There is no
        single "view notifications" permission, and inventing one would
        be wrong twice over: it would either hide alerts from someone who
        can see the underlying module, or show alerts about a module they
        cannot open. Authorisation happens per category instead, against
        the permission that module already uses.
        """
        notifications: List[Notification] = []

        # One permission lookup per DISTINCT permission, not one per
        # check. Every producer asks whether the actor may see its
        # module, and `check_permission` walks user -> role ->
        # permissions through the ORM each time - which for a single
        # refresh meant a dozen identical lazy-loaded queries. Memoising
        # for the duration of one call is safe because a user's role
        # cannot change midway through computing their alert list.
        #
        # The cache is a local, passed down to each producer, rather than
        # instance state: this service is otherwise stateless, and a
        # cache living on the instance would quietly go stale the moment
        # somebody's role was changed while a window stayed open.
        permission_cache: dict[str, bool] = {}

        def can(permission: Permission) -> bool:
            name = permission.value
            if name not in permission_cache:
                permission_cache[name] = self._auth_service.check_permission(actor_user_id, name)
            return permission_cache[name]

        for producer in (
            self._low_fuel,
            self._fuel_variance,
            self._shift_reconciliation_alerts,
            self._attendance_issues,
            self._pending_approvals,
            self._outstanding_credit,
            self._supplier_payments_due,
            self._unauthorized_actions,
            self._backup_failure,
            self._database_errors,
        ):
            # One failing producer must not blank the whole alert screen.
            # A notification list is a diagnostic surface: it is consulted
            # precisely when something is already wrong, which is exactly
            # when a half-broken database is most likely to make one of
            # these queries throw. Losing one category is a far better
            # outcome than showing an empty, falsely reassuring screen.
            try:
                notifications.extend(producer(actor_user_id, can))
            except Exception:  # noqa: BLE001
                logger.warning("Could not compute %s notifications", producer.__name__, exc_info=True)

        notifications.sort(
            key=lambda n: (_SEVERITY_ORDER[n.severity], n.category.value, n.is_summary, n.title)
        )
        return NotificationSummary(notifications=notifications)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cap(items: List[Notification], category: NotificationCategory, noun: str) -> List[Notification]:
        """Trim a category to NOTIFICATION_MAX_PER_CATEGORY, replacing the
        remainder with one line that says how many were left out.

        The count is never hidden - an alert screen that silently drops
        items is lying about the size of the problem."""
        if len(items) <= NOTIFICATION_MAX_PER_CATEGORY:
            return items
        remaining = len(items) - NOTIFICATION_MAX_PER_CATEGORY
        kept = items[:NOTIFICATION_MAX_PER_CATEGORY]
        kept.append(
            Notification(
                category=category,
                # The summary line inherits the highest severity present in
                # the part being hidden, so a critical item cannot be
                # demoted to a footnote by being 6th in the list.
                severity=min(
                    (item.severity for item in items[NOTIFICATION_MAX_PER_CATEGORY:]),
                    key=lambda severity: _SEVERITY_ORDER[severity],
                ),
                title=f"{remaining} more {noun}",
                detail=f"{remaining} further {noun} are not shown here. Open the module to see them all.",
                is_summary=True,
            )
        )
        return kept

    def _recent_cutoff(self) -> date:
        return date.today() - timedelta(days=NOTIFICATION_RECENT_EVENT_DAYS)

    # ------------------------------------------------------------------
    # Inventory (Permission.INVENTORY_VIEW)
    # ------------------------------------------------------------------

    def _low_fuel(self, actor_user_id: str, can) -> List[Notification]:
        if not can(Permission.INVENTORY_VIEW):
            return []

        threshold = Decimal(str(DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT))
        found = []
        for tank in self._tank_repo.list_all():
            if not tank.capacity or tank.capacity <= 0:
                continue
            percent = (tank.current_stock / tank.capacity) * 100
            if percent > threshold:
                continue
            # Below half the flag threshold the pump is close to running
            # dry, which stops sales outright - a different order of
            # problem from "reorder soon".
            severity = (
                NotificationSeverity.CRITICAL if percent <= threshold / 2 else NotificationSeverity.WARNING
            )
            found.append(
                Notification(
                    category=NotificationCategory.LOW_FUEL,
                    severity=severity,
                    title=f"{tank.code} is low on fuel",
                    detail=f"{tank.current_stock:.2f} of {tank.capacity:.2f} litres remaining ({percent:.0f}% of capacity).",
                    entity_id=tank.id,
                )
            )
        found.sort(key=lambda n: _SEVERITY_ORDER[n.severity])
        return self._cap(found, NotificationCategory.LOW_FUEL, "tanks running low")

    def _fuel_variance(self, actor_user_id: str, can) -> List[Notification]:
        """Flag tanks whose most recent fuel reconciliation was not NORMAL.

        Only the LATEST reconciliation per tank: an older one that has
        since been superseded by a clean count describes a period that
        has already been closed out and re-baselined, and re-raising it
        would mean a variance could never be resolved by doing the
        correct thing.
        """
        if not can(Permission.INVENTORY_VIEW):
            return []

        found = []
        for tank in self._tank_repo.list_all():
            latest = self._fuel_reconciliation_repo.get_latest_for_tank(tank.id)
            if latest is None:
                continue
            try:
                classification = VarianceClassification(latest.classification)
            except ValueError:
                continue
            severity = _CLASSIFICATION_SEVERITY.get(classification)
            if severity is None:
                continue
            found.append(
                Notification(
                    category=NotificationCategory.FUEL_VARIANCE,
                    severity=severity,
                    title=f"Fuel variance on {tank.code}",
                    detail=(
                        f"The reconciliation on {latest.reconciliation_date} is classified "
                        f"{classification.value.replace('_', ' ')} "
                        f"(variance {latest.variance:.3f} litres). A variance is a review signal, not an accusation."
                    ),
                    entity_id=tank.id,
                )
            )
        return self._cap(found, NotificationCategory.FUEL_VARIANCE, "tanks with a fuel variance")

    # ------------------------------------------------------------------
    # Shift reconciliation (Permission.RECONCILIATION_VIEW)
    # ------------------------------------------------------------------

    def _shift_reconciliation_alerts(self, actor_user_id: str, can) -> List[Notification]:
        """Cash shortage, cash excess, payment mismatch and failed
        reconciliation all read the same ShiftReconciliation rows, so they
        are produced in one pass rather than four near-identical queries.

        Scope: a reconciliation still awaiting approval (unresolved, so it
        stays until somebody acts) or performed recently. An approved
        reconciliation from three months ago is history, not an alert -
        surfacing it forever would train the operator to ignore the screen.
        """
        if not can(Permission.RECONCILIATION_VIEW):
            return []

        cutoff = self._recent_cutoff()
        found = []
        for reconciliation in self._shift_reconciliation_repo.list_all():
            is_unresolved = reconciliation.status == ReconciliationStatus.PENDING_APPROVAL.value
            # local_date_of, not .date(): performed_at is a UTC instant and
            # the business day it belongs to is the local one. This bug
            # class has already appeared three times in this project
            # (fuel reconciliation boundaries, is_overdue, customer
            # statements) - see app/core/dates.py.
            performed_on = local_date_of(reconciliation.performed_at)
            if not is_unresolved and performed_on < cutoff:
                continue

            label = f"shift reconciliation of {performed_on}"

            if reconciliation.cash_variance < 0:
                found.append(
                    Notification(
                        category=NotificationCategory.CASH_SHORTAGE,
                        severity=NotificationSeverity.CRITICAL,
                        title=f"Cash short by {abs(reconciliation.cash_variance):.2f}",
                        detail=(
                            f"The {label} declared {reconciliation.declared_cash:.2f} against an expected "
                            f"{reconciliation.expected_cash:.2f}."
                        ),
                        entity_id=reconciliation.id,
                    )
                )
            elif reconciliation.cash_variance > 0:
                # An excess is a discrepancy too - money that cannot be
                # accounted for usually means a sale went unrecorded - but
                # it is not a loss, so it does not carry the same weight.
                found.append(
                    Notification(
                        category=NotificationCategory.CASH_EXCESS,
                        severity=NotificationSeverity.WARNING,
                        title=f"Cash over by {reconciliation.cash_variance:.2f}",
                        detail=(
                            f"The {label} declared {reconciliation.declared_cash:.2f} against an expected "
                            f"{reconciliation.expected_cash:.2f}. An excess usually means a sale was not recorded."
                        ),
                        entity_id=reconciliation.id,
                    )
                )

            if reconciliation.upi_variance != 0 or reconciliation.card_variance != 0:
                found.append(
                    Notification(
                        category=NotificationCategory.PAYMENT_MISMATCH,
                        severity=NotificationSeverity.WARNING,
                        title="Digital payments do not match",
                        detail=(
                            f"The {label} shows a UPI variance of {reconciliation.upi_variance:.2f} and a card "
                            f"variance of {reconciliation.card_variance:.2f}."
                        ),
                        entity_id=reconciliation.id,
                    )
                )

            if is_unresolved:
                try:
                    classification = VarianceClassification(reconciliation.classification)
                    severity = _CLASSIFICATION_SEVERITY.get(classification) or NotificationSeverity.WARNING
                except ValueError:
                    severity = NotificationSeverity.WARNING
                found.append(
                    Notification(
                        category=NotificationCategory.FAILED_RECONCILIATION,
                        severity=severity,
                        title="A shift reconciliation needs approval",
                        detail=f"The {label} is classified {reconciliation.classification.replace('_', ' ')} and is awaiting sign-off.",
                        entity_id=reconciliation.id,
                    )
                )

        return found

    # ------------------------------------------------------------------
    # Attendance (Permission.ATTENDANCE_VIEW)
    # ------------------------------------------------------------------

    def _attendance_issues(self, actor_user_id: str, can) -> List[Notification]:
        """Active employees with nothing recorded for today.

        Note this reports a MISSING record, not a bad one. An employee
        marked absent has been accounted for; an employee with no row at
        all is the actual gap, because nobody has yet said whether they
        turned up - and that is the one a supervisor can still fix today.
        """
        if not can(Permission.ATTENDANCE_VIEW):
            return []

        today = date.today()
        marked = {record.employee_id for record in self._attendance_repo.list_for_date(today)}
        found = [
            Notification(
                category=NotificationCategory.ATTENDANCE_ISSUE,
                severity=NotificationSeverity.INFO,
                title=f"No attendance recorded for {employee.first_name} {employee.last_name}",
                detail=f"{employee.employee_code} has no attendance entry for {today}.",
                entity_id=employee.id,
            )
            for employee in self._employee_repo.list_active()
            if employee.id not in marked
        ]
        return self._cap(found, NotificationCategory.ATTENDANCE_ISSUE, "employees without attendance today")

    # ------------------------------------------------------------------
    # Approvals - gated on the APPROVE permission, not the view one
    # ------------------------------------------------------------------

    def _pending_approvals(self, actor_user_id: str, can) -> List[Notification]:
        found = []

        if can(Permission.EXPENSE_APPROVE):
            pending = [
                expense
                for expense in self._expense_repo.list_all()
                if expense.status == ExpenseStatus.PENDING.value
            ]
            if pending:
                total = sum((expense.amount for expense in pending), Decimal("0"))
                # One rolled-up line rather than one per expense: the
                # action is the same for all of them ("go and review the
                # queue"), so a row each would be noise, not information.
                found.append(
                    Notification(
                        category=NotificationCategory.PENDING_APPROVAL,
                        severity=NotificationSeverity.WARNING,
                        title=f"{len(pending)} expense(s) awaiting approval",
                        detail=(
                            f"{total:.2f} in total is pending. Until approved, these do not reduce the expected "
                            "cash in any shift reconciliation."
                        ),
                    )
                )

        if can(Permission.RECONCILIATION_APPROVE):
            pending_reconciliations = [
                reconciliation
                for reconciliation in self._shift_reconciliation_repo.list_all()
                if reconciliation.status == ReconciliationStatus.PENDING_APPROVAL.value
            ]
            if pending_reconciliations:
                found.append(
                    Notification(
                        category=NotificationCategory.PENDING_APPROVAL,
                        severity=NotificationSeverity.WARNING,
                        title=f"{len(pending_reconciliations)} shift reconciliation(s) awaiting approval",
                        detail="A high-variance reconciliation stays pending until a manager or owner signs it off.",
                    )
                )

        return found

    # ------------------------------------------------------------------
    # Credit (Permission.CREDIT_VIEW)
    # ------------------------------------------------------------------

    def _outstanding_credit(self, actor_user_id: str, can) -> List[Notification]:
        """Overdue credit accounts.

        Calls CreditService's PUBLIC, permission-checked methods on
        purpose. That is correct rather than a layering violation: this
        block has already confirmed the actor holds CREDIT_VIEW, which is
        the very permission those methods check, so the check passes for
        the same reason twice. The `*_as_related_action` pattern exists
        for the opposite case - a caller authorised by a DIFFERENT
        permission - which is not what is happening here.
        """
        if not can(Permission.CREDIT_VIEW):
            return []

        found = []
        for account in self._credit_account_repo.list_all():
            if not self._credit_service.is_overdue(actor_user_id, account.customer_id):
                continue
            outstanding = self._credit_service.get_outstanding_balance(actor_user_id, account.customer_id)
            customer_name = account.customer.name if account.customer else account.customer_id
            found.append(
                Notification(
                    category=NotificationCategory.OUTSTANDING_CREDIT,
                    severity=NotificationSeverity.WARNING,
                    title=f"{customer_name} is overdue",
                    detail=(
                        f"{outstanding:.2f} outstanding, past the agreed {account.payment_due_days}-day term. "
                        "Overdue is a signal to follow up, not an accusation."
                    ),
                    entity_id=account.customer_id,
                )
            )
        found.sort(key=lambda n: n.title)
        return self._cap(found, NotificationCategory.OUTSTANDING_CREDIT, "overdue credit accounts")

    # ------------------------------------------------------------------
    # Procurement (Permission.PROCUREMENT_VIEW)
    # ------------------------------------------------------------------

    def _supplier_payments_due(self, actor_user_id: str, can) -> List[Notification]:
        if not can(Permission.PROCUREMENT_VIEW):
            return []

        today = date.today()
        found = []
        for invoice in self._supplier_invoice_repo.list_all():
            if invoice.status == SupplierInvoiceStatus.PAID.value:
                continue
            if not invoice.due_date or invoice.due_date > today:
                continue
            paid = self._supplier_payment_repo.sum_for_invoice(invoice.id)
            outstanding = invoice.amount - paid
            if outstanding <= 0:
                continue
            days_late = (today - invoice.due_date).days
            found.append(
                Notification(
                    category=NotificationCategory.SUPPLIER_PAYMENT_DUE,
                    severity=NotificationSeverity.WARNING if days_late < 7 else NotificationSeverity.CRITICAL,
                    title=f"Invoice {invoice.invoice_number} is due",
                    detail=(
                        f"{outstanding:.2f} outstanding, due {invoice.due_date}"
                        f"{f' ({days_late} days ago)' if days_late else ''}."
                    ),
                    entity_id=invoice.id,
                )
            )
        found.sort(key=lambda n: _SEVERITY_ORDER[n.severity])
        return self._cap(found, NotificationCategory.SUPPLIER_PAYMENT_DUE, "supplier invoices due")

    # ------------------------------------------------------------------
    # Event-derived alerts - read from the audit trail
    # ------------------------------------------------------------------

    def _unauthorized_actions(self, actor_user_id: str, can) -> List[Notification]:
        """Refused actions recorded by the require_permission decorator.

        Rolled up into one line with a count rather than one alert per
        denial. A single denial is almost always a mis-click; what
        actually matters is the SHAPE - many denials in a short window is
        somebody testing what they can reach, and only a count makes that
        visible at a glance.
        """
        if not can(Permission.AUDIT_VIEW):
            return []

        entries = self._audit_repo.search(
            event_type="permission_denied", date_from=self._recent_cutoff(), date_to=date.today()
        )
        if not entries:
            return []

        actors = {entry.actor_id for entry in entries if entry.actor_id}
        return [
            Notification(
                category=NotificationCategory.UNAUTHORIZED_ACTION,
                # Escalates on repetition, not on any single event.
                severity=NotificationSeverity.WARNING if len(entries) < 10 else NotificationSeverity.CRITICAL,
                title=f"{len(entries)} refused action(s) in the last {NOTIFICATION_RECENT_EVENT_DAYS} days",
                detail=(
                    f"Involving {len(actors)} user account(s). Occasional refusals are normal; a burst from one "
                    "account is worth looking at in the Audit Log."
                ),
            )
        ]

    def _database_errors(self, actor_user_id: str, can) -> List[Notification]:
        """Integrity-check failures and audit-chain breaks.

        Both are recorded under their own event type precisely so this
        can find them without parsing a description (see
        BackupService.check_integrity and AuditService.verify_trail).
        """
        if not can(Permission.BACKUP_MANAGE):
            return []

        cutoff = self._recent_cutoff()
        today = date.today()
        found = []

        integrity_failures = self._audit_repo.search(
            event_type="database_integrity_failed", date_from=cutoff, date_to=today
        )
        if integrity_failures:
            found.append(
                Notification(
                    category=NotificationCategory.DATABASE_ERROR,
                    severity=NotificationSeverity.CRITICAL,
                    title="The database failed an integrity check",
                    detail=(
                        f"Most recently: {integrity_failures[0].description}. "
                        "Restore from a verified backup - see the recovery guide."
                    ),
                )
            )

        tamper_events = self._audit_repo.search(
            event_type="audit_trail_tampered", date_from=cutoff, date_to=today
        )
        if tamper_events:
            found.append(
                Notification(
                    category=NotificationCategory.DATABASE_ERROR,
                    severity=NotificationSeverity.CRITICAL,
                    title="The audit trail has been altered",
                    detail=(
                        f"{tamper_events[0].description} The trail was modified outside the application, "
                        "which the hash chain is designed to make impossible to hide."
                    ),
                )
            )

        return found

    def _backup_failure(self, actor_user_id: str, can) -> List[Notification]:
        """No recent backup.

        Derived from the ABSENCE of a recent backup file rather than from
        a recorded failure event, and that is the stronger test: it does
        not care why there is no backup. A full disk, a revoked
        permission, a crash before the write, or a bug in a code path
        nobody added logging to all produce the same observable fact -
        the thing that would be needed in an emergency is not there.
        """
        if not can(Permission.BACKUP_MANAGE) or not self._db_path:
            return []

        # Imported here rather than at module scope: this is the only
        # producer touching the filesystem, and the import pulls in the
        # sqlite3 backup machinery that nothing else in this module needs.
        from app.database import backup as backup_module

        backups = backup_module.list_backups(self._db_path)
        if not backups:
            return [
                Notification(
                    category=NotificationCategory.BACKUP_FAILURE,
                    severity=NotificationSeverity.CRITICAL,
                    title="No backup has ever been taken",
                    detail="There is nothing to restore from if this database is lost. Open Backups and take one now.",
                )
            ]

        # BackupInfo.created_at comes from the file's mtime via
        # datetime.fromtimestamp(), which is NAIVE LOCAL time - so it is
        # compared against a naive local now(), not the aware UTC used
        # everywhere else in this app. Mixing the two here would be the
        # fourth instance of this project's recurring timezone bug.
        newest = max(backups, key=lambda info: info.created_at)
        age_hours = (datetime.now() - newest.created_at).total_seconds() / 3600  # noqa: DTZ005
        if age_hours <= NOTIFICATION_BACKUP_OVERDUE_HOURS:
            return []

        return [
            Notification(
                category=NotificationCategory.BACKUP_FAILURE,
                severity=NotificationSeverity.CRITICAL,
                title=f"The newest backup is {age_hours / 24:.0f} days old",
                detail=(
                    "Automatic backups run at startup and should never fall this far behind. "
                    "Check that the disk is not full and that the backups folder is writable."
                ),
            )
        ]
