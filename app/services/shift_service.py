"""
Shift service layer (problemstatement.md #11): open a shift, assign
attendants to nozzles with opening meter readings, complete those
assignments with closing meter readings, and close the shift. A closed
shift is not freely editable — changing it again requires reopen_shift,
which is a stricter permission, requires a reason, and is audit-logged.

Full cash/UPI/card/fuel reconciliation is deferred to Phase 15, once the
sales/payments/inventory modules this depends on exist.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.core.constants import AssignmentStatus, Permission, ShiftStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.nozzle_assignment import NozzleAssignment
from app.models.shift import Shift
from app.repositories.base import session_for, unit_of_work
from app.schemas.shift import NozzleAssignmentComplete, NozzleAssignmentCreate, ShiftOpen


class ShiftService:
    def __init__(
        self, shift_repo, assignment_repo, employee_repo, nozzle_repo, user_repo, audit_repo, auth_service,
        sale_service=None,
    ):
        self._shift_repo = shift_repo
        self._assignment_repo = assignment_repo
        self._employee_repo = employee_repo
        self._nozzle_repo = nozzle_repo
        self._user_repo = user_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        # Optional: SaleService itself depends on TankService/CreditService,
        # which the composition root (main_window.py) builds after
        # ShiftService, so this is usually wired in afterwards via
        # attach_sale_service rather than passed in here directly. None
        # is a valid, supported state - see complete_nozzle_assignment,
        # which simply skips the cash auto-settlement step without it
        # (every other ShiftService behavior is unaffected).
        self._sale_service = sale_service
        self._session = session_for(shift_repo)

    def attach_sale_service(self, sale_service) -> None:
        """Wire in SaleService after both services exist - see the
        constructor comment on why this can't always happen at
        construction time."""
        self._sale_service = sale_service

    @require_permission(Permission.SHIFT_MANAGE.value)
    def open_shift(self, actor_user_id: str, data: ShiftOpen) -> Shift:
        if self._shift_repo.get_by_date_and_label(data.shift_date, data.shift_label):
            raise ConflictError(f"A shift already exists for {data.shift_date} / {data.shift_label}")

        if data.supervisor_id and not self._user_repo.get_by_id(data.supervisor_id):
            raise NotFoundError(f"Supervisor not found: {data.supervisor_id}")

        shift = Shift(
            shift_date=data.shift_date,
            shift_label=data.shift_label,
            start_time=datetime.now(timezone.utc),
            opened_by_id=actor_user_id,
            supervisor_id=data.supervisor_id,
            notes=data.notes,
            status=ShiftStatus.OPEN.value,
        )
        shift = self._shift_repo.add(shift)
        self._audit_repo.record(
            event_type="shift_opened",
            actor_id=actor_user_id,
            entity_type="Shift",
            entity_id=shift.id,
            description=f"Opened {data.shift_label} shift for {data.shift_date}",
        )
        return shift

    @require_permission(Permission.SHIFT_MANAGE.value)
    def assign_nozzle(self, actor_user_id: str, shift_id: str, data: NozzleAssignmentCreate) -> NozzleAssignment:
        shift = self._get_shift_or_raise(shift_id)
        if shift.status != ShiftStatus.OPEN.value:
            raise ConflictError("Cannot assign a nozzle on a shift that is not open")

        if not self._employee_repo.get_by_id(data.employee_id):
            raise NotFoundError(f"Employee not found: {data.employee_id}")

        nozzle = self._nozzle_repo.get_by_id(data.nozzle_id)
        if not nozzle:
            raise NotFoundError(f"Nozzle not found: {data.nozzle_id}")
        if nozzle.status != "active":
            raise ConflictError(f"Nozzle {nozzle.code} is not active ({nozzle.status})")

        if self._assignment_repo.get_active_for_employee_in_shift(shift_id, data.employee_id):
            raise ConflictError("This employee already has an active nozzle assignment for this shift")
        if self._assignment_repo.get_active_for_nozzle_in_shift(shift_id, data.nozzle_id):
            raise ConflictError("This nozzle is already actively assigned to another employee for this shift")

        assignment = NozzleAssignment(
            employee_id=data.employee_id,
            nozzle_id=data.nozzle_id,
            shift_id=shift_id,
            opening_meter=data.opening_meter,
            assigned_by_id=actor_user_id,
            remarks=data.remarks,
            status=AssignmentStatus.ACTIVE.value,
        )
        assignment = self._assignment_repo.add(assignment)
        self._audit_repo.record(
            event_type="nozzle_assigned",
            actor_id=actor_user_id,
            entity_type="NozzleAssignment",
            entity_id=assignment.id,
            description=f"Assigned employee {data.employee_id} to nozzle {data.nozzle_id} for shift {shift_id}",
        )
        return assignment

    @require_permission(Permission.SHIFT_MANAGE.value)
    def complete_nozzle_assignment(
        self, actor_user_id: str, assignment_id: str, data: NozzleAssignmentComplete
    ) -> NozzleAssignment:
        """Completing the assignment and auto-settling its remaining cash
        into one Sale (see SaleService.settle_assignment_cash) are wrapped
        in one transaction — unit_of_work nests cleanly into the Sale
        write's own inner one (app/repositories/base.py) — so a failure
        partway through can never leave the assignment closed with its
        cash never accounted for.
        """
        with unit_of_work(self._session):
            return self._complete_nozzle_assignment_impl(actor_user_id, assignment_id, data)

    def _complete_nozzle_assignment_impl(
        self, actor_user_id: str, assignment_id: str, data: NozzleAssignmentComplete
    ) -> NozzleAssignment:
        assignment = self._get_assignment_or_raise(assignment_id)
        if assignment.status != AssignmentStatus.ACTIVE.value:
            raise ConflictError("Only an active assignment can be completed")
        if data.closing_meter < assignment.opening_meter:
            raise ValueError("closing_meter cannot be less than opening_meter")

        assignment.closing_meter = data.closing_meter
        assignment.end_time = datetime.now(timezone.utc)
        assignment.status = AssignmentStatus.COMPLETED.value
        assignment = self._assignment_repo.update(assignment)
        self._audit_repo.record(
            event_type="nozzle_assignment_completed",
            actor_id=actor_user_id,
            entity_type="NozzleAssignment",
            entity_id=assignment.id,
            description=f"Closing meter {data.closing_meter}",
        )

        if self._sale_service is not None:
            self._sale_service.settle_assignment_cash(actor_user_id, assignment)

        return assignment

    @require_permission(Permission.SHIFT_MANAGE.value)
    def cancel_nozzle_assignment(self, actor_user_id: str, assignment_id: str, reason: str) -> NozzleAssignment:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to cancel a nozzle assignment")

        assignment = self._get_assignment_or_raise(assignment_id)
        if assignment.status != AssignmentStatus.ACTIVE.value:
            raise ConflictError("Only an active assignment can be cancelled")

        assignment.status = AssignmentStatus.CANCELLED.value
        assignment.end_time = datetime.now(timezone.utc)
        assignment.remarks = reason.strip()
        assignment = self._assignment_repo.update(assignment)
        self._audit_repo.record(
            event_type="nozzle_assignment_cancelled",
            actor_id=actor_user_id,
            entity_type="NozzleAssignment",
            entity_id=assignment.id,
            description=reason.strip(),
        )
        return assignment

    @require_permission(Permission.SHIFT_MANAGE.value)
    def close_shift(self, actor_user_id: str, shift_id: str, notes: Optional[str] = None) -> Shift:
        shift = self._get_shift_or_raise(shift_id)
        if shift.status != ShiftStatus.OPEN.value:
            raise ConflictError("Shift is not open")

        still_active = [a for a in self._assignment_repo.list_for_shift(shift_id) if a.status == AssignmentStatus.ACTIVE.value]
        if still_active:
            raise ConflictError(
                f"{len(still_active)} nozzle assignment(s) are still active; "
                "complete or cancel them before closing the shift"
            )

        shift.status = ShiftStatus.CLOSED.value
        shift.end_time = datetime.now(timezone.utc)
        shift.closed_by_id = actor_user_id
        if notes:
            shift.notes = f"{shift.notes}\n{notes}" if shift.notes else notes
        shift = self._shift_repo.update(shift)
        self._audit_repo.record(
            event_type="shift_closed",
            actor_id=actor_user_id,
            entity_type="Shift",
            entity_id=shift.id,
            description=notes,
        )
        return shift

    @require_permission(Permission.SHIFT_REOPEN.value)
    def reopen_shift(self, actor_user_id: str, shift_id: str, reason: str) -> Shift:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to reopen a shift")

        shift = self._get_shift_or_raise(shift_id)
        if shift.status != ShiftStatus.CLOSED.value:
            raise ConflictError("Only a closed shift can be reopened")

        shift.status = ShiftStatus.OPEN.value
        shift.reopen_reason = reason.strip()
        shift.reopened_by_id = actor_user_id
        shift.reopened_at = datetime.now(timezone.utc)
        shift = self._shift_repo.update(shift)
        self._audit_repo.record(
            event_type="shift_reopened",
            actor_id=actor_user_id,
            entity_type="Shift",
            entity_id=shift.id,
            description=reason.strip(),
            old_value=ShiftStatus.CLOSED.value,
            new_value=ShiftStatus.OPEN.value,
        )
        return shift

    @require_permission(Permission.SHIFT_VIEW.value)
    def get_shift(self, actor_user_id: str, shift_id: str) -> Shift:
        return self._get_shift_or_raise(shift_id)

    @require_permission(Permission.SHIFT_VIEW.value)
    def list_shifts(self, actor_user_id: str, date_from=None, date_to=None) -> List[Shift]:
        return self._shift_repo.list_for_date_range(date_from, date_to)

    @require_permission(Permission.SHIFT_VIEW.value)
    def list_nozzle_assignments(self, actor_user_id: str, shift_id: str) -> List[NozzleAssignment]:
        self._get_shift_or_raise(shift_id)
        return self._assignment_repo.list_for_shift(shift_id)

    @require_permission(Permission.SHIFT_VIEW.value)
    def list_active_nozzles(self, actor_user_id: str):
        return self._nozzle_repo.list_active()

    @require_permission(Permission.MY_ASSIGNMENT_VIEW.value)
    def get_my_active_assignment(self, actor_user_id: str) -> Optional[NozzleAssignment]:
        """The acting user's own current nozzle/fuel assignment, if any —
        problemstatement.md #38: an attendant should see "My Nozzle".
        Returns None (not NotFoundError) when there's simply nothing to
        show: no linked Employee record, or no active assignment right now.
        """
        employee = self._employee_repo.get_by_user_id(actor_user_id)
        if not employee:
            return None
        return self._assignment_repo.get_active_for_employee(employee.id)

    def _get_shift_or_raise(self, shift_id: str) -> Shift:
        shift = self._shift_repo.get_by_id(shift_id)
        if not shift:
            raise NotFoundError(f"Shift not found: {shift_id}")
        return shift

    def _get_assignment_or_raise(self, assignment_id: str) -> NozzleAssignment:
        assignment = self._assignment_repo.get_by_id(assignment_id)
        if not assignment:
            raise NotFoundError(f"Nozzle assignment not found: {assignment_id}")
        return assignment
