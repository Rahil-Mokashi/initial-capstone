"""Shift close entry: how the data-entry person actually types a shift (site visit, owner's correction).

Attendants never log in and there is no per-transaction record. After the shift the cashier types, per nozzle, the CLOSING
master reading (and testing litres); the opening reading is the nozzle's last closing reading. This service turns that into
the existing nozzle assignment + completion, so the app's own rule still applies: the part of the meter not already billed
as a credit sale becomes one cash sale, and the checks compare litres against the meters.

The existing model wants an employee on every assignment. Since nobody is named per nozzle, each nozzle gets one stand-in
record ("Nozzle N1 (shift entry)", code NOZZLE-N1) created on first use. NEEDS HUMAN REVIEW: these stand-ins appear in the
employee list; hiding them or dropping the employee requirement would change existing models.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import volume
from app.core.permissions import require_permission
from app.models.employee import Employee
from app.repositories.base import session_for, unit_of_work
from app.schemas.shift import NozzleAssignmentComplete, NozzleAssignmentCreate

STAND_IN_PREFIX = "NOZZLE-"


@dataclass
class NozzleLine:
    nozzle_id: str
    code: str
    fuel: str
    tank: Optional[str]
    opening: Optional[Decimal]  # last closing reading, if the nozzle has ever been closed
    closed: bool  # already closed in this shift
    closing: Optional[Decimal] = None
    testing: Decimal = Decimal("0")


@dataclass
class Reading:
    nozzle_id: str
    closing: Decimal
    testing: Decimal = Decimal("0")
    opening: Optional[Decimal] = None  # only needed the first time a nozzle is ever used


class ShiftCloseService:
    def __init__(self, shift_service, shift_repo, assignment_repo, nozzle_repo, employee_repo, audit_repo, auth_service):
        self._shifts = shift_service
        self._shift_repo = shift_repo
        self._assignments = assignment_repo
        self._nozzles = nozzle_repo
        self._employees = employee_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(shift_repo)

    def _last_closing(self, nozzle_id: str) -> Optional[Decimal]:
        from app.models.nozzle_assignment import NozzleAssignment

        row = (
            self._session.query(NozzleAssignment)
            .filter(NozzleAssignment.nozzle_id == nozzle_id, NozzleAssignment.closing_meter.isnot(None))
            .order_by(NozzleAssignment.end_time.desc(), NozzleAssignment.created_at.desc())
            .first()
        )
        return row.closing_meter if row is not None else None

    @require_permission(Permission.SHIFT_VIEW.value)
    def sheet(self, actor_user_id: str, shift_id: str) -> List[NozzleLine]:
        shift = self._shift_repo.get_by_id(shift_id)
        if shift is None:
            raise NotFoundError(f"Shift not found: {shift_id}")
        mine = {a.nozzle_id: a for a in self._assignments.list_for_shift(shift_id) if a.status != "cancelled"}
        out = []
        for n in sorted(self._nozzles.list_all(), key=lambda n: n.code):
            if n.status != "active":
                continue
            a = mine.get(n.id)
            out.append(NozzleLine(
                nozzle_id=n.id, code=n.code, fuel=n.fuel.fuel_type if n.fuel else "", tank=n.tank.code if n.tank else None,
                opening=a.opening_meter if a else self._last_closing(n.id), closed=bool(a and a.closing_meter is not None),
                closing=a.closing_meter if a and a.closing_meter is not None else None,
                testing=a.testing_volume if a else Decimal("0"),
            ))
        return out

    def _stand_in(self, actor_user_id: str, nozzle) -> Employee:
        code = f"{STAND_IN_PREFIX}{nozzle.code}"
        emp = self._employees.get_by_code(code) if hasattr(self._employees, "get_by_code") else None
        if emp is None:
            emp = self._session.query(Employee).filter_by(employee_code=code).first()
        if emp is None:
            emp = self._employees.add(Employee(
                employee_code=code, first_name=f"Nozzle {nozzle.code}", last_name="(shift entry)", contact_number="-",
                joining_date=date.today(), designation="Stand-in for shift entry", status="active",
            ))
            self._audit_repo.record(event_type="shift_entry_stand_in_created", actor_id=actor_user_id, entity_type="Employee",
                                    entity_id=emp.id, description=f"Stand-in record {code} created for typing nozzle readings without naming an attendant")
        return emp

    @require_permission(Permission.SHIFT_MANAGE.value)
    def submit(self, actor_user_id: str, shift_id: str, readings: List[Reading]) -> List[NozzleLine]:
        if not readings:
            raise ValueError("Type at least one closing reading")
        with unit_of_work(self._session):
            for r in readings:
                nozzle = self._nozzles.get_by_id(r.nozzle_id)
                if nozzle is None:
                    raise NotFoundError(f"Nozzle not found: {r.nozzle_id}")
                existing = next((a for a in self._assignments.list_for_shift(shift_id) if a.nozzle_id == r.nozzle_id and a.status != "cancelled"), None)
                if existing is not None and existing.closing_meter is not None:
                    raise ConflictError(f"{nozzle.code} is already closed for this shift")
                if existing is None:
                    opening = r.opening if r.opening is not None else self._last_closing(r.nozzle_id)
                    if opening is None:
                        raise ValueError(f"{nozzle.code} has never been closed: type its opening reading too")
                    emp = self._stand_in(actor_user_id, nozzle)
                    existing = self._shifts.assign_nozzle(actor_user_id, shift_id, NozzleAssignmentCreate(
                        employee_id=emp.id, nozzle_id=r.nozzle_id, opening_meter=volume(opening), remarks="Shift close entry"))
                if r.closing < existing.opening_meter:
                    raise ValueError(f"{nozzle.code}: the closing reading {r.closing} is below the opening {existing.opening_meter}")
                self._shifts.complete_nozzle_assignment(actor_user_id, existing.id, NozzleAssignmentComplete(
                    closing_meter=volume(r.closing), testing_volume=volume(r.testing)))
            self._audit_repo.record(event_type="shift_close_entry", actor_id=actor_user_id, entity_type="Shift", entity_id=shift_id,
                                    description=f"Closing readings typed for {len(readings)} nozzle(s)")
        return self.sheet.__wrapped__(self, actor_user_id, shift_id)
