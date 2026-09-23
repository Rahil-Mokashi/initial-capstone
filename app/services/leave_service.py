"""Leave management (problemstatement.md #2/#9/#10/#29).

Client-perspective review, 2026-09-23: "Leave" existed only as one status
value an attendance day could carry, with no request, no reason, and no
approval trail behind it - the spec names Leave as its own entity in four
separate sections. Asked how to scope the fix, the user chose the smaller
of two options: a request + approve/reject/cancel workflow, the same
shape as Expense's approve_expense/reject_expense, and explicitly NOT a
leave-balance/entitlement system (leave types, annual quotas, accrual,
carry-forward) - that is real HR policy specific to the client's pump,
not something to invent under CLAUDE.md's "do not invent business rules."
Adding balance tracking later, on top of this, remains fully open; this
module does not assume or preclude it.

Approving a request drives the *existing* Attendance tracking (via
AttendanceService.apply_leave_as_related_action) rather than duplicating
it - a leave request's whole point is to end up as LEAVE-marked attendance
days once approved, the same relationship the spec's own wording implies
("Attendance... Leave... Shift history") without needing a second,
parallel calendar.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from app.core.constants import LeaveRequestStatus, Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.leave_request import LeaveRequest
from app.repositories.base import session_for, unit_of_work
from app.schemas.leave_request import LeaveRequestCreate


class LeaveService:
    def __init__(self, leave_request_repo, employee_repo, audit_repo, auth_service, attendance_service=None):
        self._leave_request_repo = leave_request_repo
        self._employee_repo = employee_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        # Optional, like ExpenseService's tank_service: None is fully
        # supported (a request can be created/viewed without it), but
        # approve_leave_request needs it to actually update attendance -
        # see attach_attendance_service.
        self._attendance_service = attendance_service
        self._session = session_for(leave_request_repo)

    def attach_attendance_service(self, attendance_service) -> None:
        """Wire in AttendanceService after both services exist, for
        composition roots that build them in the other order - see
        ExpenseService.attach_tank_service, same reasoning."""
        self._attendance_service = attendance_service

    @require_permission(Permission.LEAVE_MANAGE.value)
    def request_leave(self, actor_user_id: str, data: LeaveRequestCreate) -> LeaveRequest:
        if not self._employee_repo.get_by_id(data.employee_id):
            raise NotFoundError(f"Employee not found: {data.employee_id}")

        overlapping = self._leave_request_repo.list_overlapping_active(
            data.employee_id, data.date_from, data.date_to
        )
        if overlapping:
            raise ConflictError(
                f"Employee {data.employee_id} already has a pending or approved leave request "
                f"overlapping {data.date_from}..{data.date_to}"
            )

        leave_request = LeaveRequest(
            employee_id=data.employee_id,
            date_from=data.date_from,
            date_to=data.date_to,
            reason=data.reason,
            status=LeaveRequestStatus.PENDING.value,
            requested_by_id=actor_user_id,
        )
        leave_request = self._leave_request_repo.add(leave_request)
        self._audit_repo.record(
            event_type="leave_requested",
            actor_id=actor_user_id,
            entity_type="LeaveRequest",
            entity_id=leave_request.id,
            description=f"Requested leave for employee {data.employee_id}, {data.date_from}..{data.date_to}",
        )
        return leave_request

    @require_permission(Permission.LEAVE_APPROVE.value)
    def approve_leave_request(self, actor_user_id: str, leave_request_id: str, remarks: str = "") -> LeaveRequest:
        """Runs as one transaction (unit_of_work): the leave request's own
        status change and every attendance day it marks LEAVE either all
        commit together or none do - a request must never end up APPROVED
        with only some of its days actually marked, which a plain
        per-write commit (the pre-2026-08-16 pattern this app moved away
        from) would allow on a failure partway through a multi-day range."""
        with unit_of_work(self._session):
            leave_request = self._get_or_raise(leave_request_id)
            if leave_request.status != LeaveRequestStatus.PENDING.value:
                raise ConflictError(f"Cannot approve a leave request with status {leave_request.status}")

            if self._attendance_service is None:
                raise ConflictError(
                    "This leave request cannot be approved: no AttendanceService is attached to mark the "
                    "corresponding attendance days - see attach_attendance_service"
                )

            leave_request.status = LeaveRequestStatus.APPROVED.value
            leave_request.decided_by_id = actor_user_id
            leave_request.decided_at = datetime.now(timezone.utc)
            leave_request.decision_reason = remarks.strip() or None
            leave_request = self._leave_request_repo.update(leave_request)

            note = f"Marked LEAVE - approved leave request {leave_request.id} ({leave_request.reason})"
            for day in _date_range(leave_request.date_from, leave_request.date_to):
                self._attendance_service.apply_leave_as_related_action(
                    actor_user_id, leave_request.employee_id, day, note
                )

            self._audit_repo.record(
                event_type="leave_approved",
                actor_id=actor_user_id,
                entity_type="LeaveRequest",
                entity_id=leave_request.id,
                description=remarks.strip() or "Approved",
            )
            return leave_request

    @require_permission(Permission.LEAVE_APPROVE.value)
    def reject_leave_request(self, actor_user_id: str, leave_request_id: str, reason: str) -> LeaveRequest:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to reject a leave request")

        leave_request = self._get_or_raise(leave_request_id)
        if leave_request.status != LeaveRequestStatus.PENDING.value:
            raise ConflictError(f"Cannot reject a leave request with status {leave_request.status}")

        leave_request.status = LeaveRequestStatus.REJECTED.value
        leave_request.decided_by_id = actor_user_id
        leave_request.decided_at = datetime.now(timezone.utc)
        leave_request.decision_reason = reason.strip()
        leave_request = self._leave_request_repo.update(leave_request)

        self._audit_repo.record(
            event_type="leave_rejected",
            actor_id=actor_user_id,
            entity_type="LeaveRequest",
            entity_id=leave_request.id,
            description=reason.strip(),
        )
        return leave_request

    @require_permission(Permission.LEAVE_MANAGE.value)
    def cancel_leave_request(self, actor_user_id: str, leave_request_id: str, reason: str) -> LeaveRequest:
        """Only from PENDING - an already-approved request has already
        changed real attendance history, and withdrawing it retroactively
        is a bigger reversal than a plain cancel; correct the Attendance
        rows directly (AttendanceService.correct_attendance) if an
        approval turns out to have been a mistake, the same way every
        other decided record in this app is corrected rather than undone."""
        if not reason or not reason.strip():
            raise ValueError("A reason is required to cancel a leave request")

        leave_request = self._get_or_raise(leave_request_id)
        if leave_request.status != LeaveRequestStatus.PENDING.value:
            raise ConflictError(f"Cannot cancel a leave request with status {leave_request.status}")

        leave_request.status = LeaveRequestStatus.CANCELLED.value
        leave_request.decided_by_id = actor_user_id
        leave_request.decided_at = datetime.now(timezone.utc)
        leave_request.decision_reason = reason.strip()
        leave_request = self._leave_request_repo.update(leave_request)

        self._audit_repo.record(
            event_type="leave_cancelled",
            actor_id=actor_user_id,
            entity_type="LeaveRequest",
            entity_id=leave_request.id,
            description=reason.strip(),
        )
        return leave_request

    @require_permission(Permission.LEAVE_VIEW.value)
    def list_leave_requests(self, actor_user_id: str) -> List[LeaveRequest]:
        return self._leave_request_repo.list_all()

    @require_permission(Permission.LEAVE_VIEW.value)
    def list_for_employee(self, actor_user_id: str, employee_id: str) -> List[LeaveRequest]:
        return self._leave_request_repo.list_for_employee(employee_id)

    def _get_or_raise(self, leave_request_id: str) -> LeaveRequest:
        leave_request = self._leave_request_repo.get_by_id(leave_request_id)
        if not leave_request:
            raise NotFoundError(f"Leave request not found: {leave_request_id}")
        return leave_request


def _date_range(date_from, date_to):
    day = date_from
    while day <= date_to:
        yield day
        day += timedelta(days=1)
