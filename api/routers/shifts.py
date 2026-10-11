"""Shifts and nozzle assignments, plus the attendant's own view.
Same ShiftService calls as app/ui/shift_window.py and app/ui/my_shift_window.py."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, OptionalReason, Out, VolumeIn, VolumeOut
from api.services import Services
from app.schemas.shift import NozzleAssignmentComplete, NozzleAssignmentCreate, ShiftOpen

router = APIRouter(tags=["shifts"])


class ShiftOut(Out):
    id: str
    shift_date: date
    shift_label: str
    status: str
    opened_by: Optional[str] = None
    notes: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    reopen_reason: Optional[str] = None


class AssignmentOut(Out):
    id: str
    shift_id: str
    employee_id: str
    employee: Optional[str] = None
    nozzle_id: str
    nozzle: Optional[str] = None
    opening_meter: VolumeOut
    closing_meter: Optional[VolumeOut] = None
    testing_volume: VolumeOut
    internal_consumption_volume: VolumeOut
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class IdLabel(Out):
    id: str
    label: str


class AssignOptions(Out):
    employees: list[IdLabel]
    nozzles: list[IdLabel]


class MyShiftOut(Out):
    shift_label: str
    shift_date: date
    nozzle: Optional[str] = None
    fuel_type: Optional[str] = None
    dispenser: Optional[str] = None
    opening_meter: VolumeOut
    status: str


class OpenShiftIn(In):
    shift_date: date
    shift_label: str
    notes: Optional[str] = None


class CloseShiftIn(In):
    notes: Optional[str] = None


class ReopenIn(In):
    reason: OptionalReason


class AssignIn(In):
    employee_id: str
    nozzle_id: str
    opening_meter: VolumeIn


class CompleteIn(In):
    closing_meter: VolumeIn
    testing_volume: VolumeIn = "0"
    internal_consumption_volume: VolumeIn = "0"


class CancelAssignmentIn(In):
    reason: OptionalReason


def shift_out(s) -> ShiftOut:
    return ShiftOut(
        id=s.id,
        shift_date=s.shift_date,
        shift_label=s.shift_label,
        status=s.status,
        opened_by=s.opened_by.username if s.opened_by else None,
        notes=s.notes,
        start_time=s.start_time,
        end_time=s.end_time,
        reopen_reason=s.reopen_reason,
    )


def assignment_out(a) -> AssignmentOut:
    e = a.employee
    return AssignmentOut(
        id=a.id,
        shift_id=a.shift_id,
        employee_id=a.employee_id,
        employee=f"{e.first_name} {e.last_name}" if e else None,
        nozzle_id=a.nozzle_id,
        nozzle=a.nozzle.code if a.nozzle else None,
        opening_meter=a.opening_meter,
        closing_meter=a.closing_meter,
        testing_volume=a.testing_volume,
        internal_consumption_volume=a.internal_consumption_volume,
        status=a.status,
        start_time=a.start_time,
        end_time=a.end_time,
    )


@router.get("/shifts", response_model=list[ShiftOut])
def list_shifts(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
):
    """Optional date window; the attendance dialogs list only the shifts of one day."""
    return [shift_out(s) for s in services.shifts.list_shifts(user.id, date_from=date_from, date_to=date_to)]


@router.post("/shifts", response_model=ShiftOut, status_code=201)
def open_shift(body: OpenShiftIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return shift_out(services.shifts.open_shift(user.id, ShiftOpen(**body.model_dump())))


@router.get("/shifts/assign-options", response_model=AssignOptions)
def assign_options(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """What the Assign Nozzle dialog lists: every employee and every active nozzle."""
    return AssignOptions(
        employees=[
            IdLabel(id=e.id, label=f"{e.employee_code} - {e.first_name} {e.last_name}")
            for e in services.employees.list_employees(user.id)
        ],
        nozzles=[IdLabel(id=n.id, label=n.code) for n in services.shifts.list_active_nozzles(user.id)],
    )


@router.get("/shifts/mine", response_model=Optional[MyShiftOut])
def my_shift(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    a = services.shifts.get_my_active_assignment(user.id)
    if a is None:
        return None
    n = a.nozzle
    return MyShiftOut(
        shift_label=a.shift.shift_label,
        shift_date=a.shift.shift_date,
        nozzle=n.code if n else None,
        fuel_type=n.fuel.fuel_type if n and n.fuel else None,
        dispenser=n.dispenser.code if n and n.dispenser else None,
        opening_meter=a.opening_meter,
        status=a.status,
    )


@router.get("/shifts/{shift_id}", response_model=ShiftOut)
def get_shift(shift_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return shift_out(services.shifts.get_shift(user.id, shift_id))


@router.post("/shifts/{shift_id}/close", response_model=ShiftOut)
def close_shift(shift_id: str, body: CloseShiftIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return shift_out(services.shifts.close_shift(user.id, shift_id, body.notes))


@router.post("/shifts/{shift_id}/reopen", response_model=ShiftOut)
def reopen_shift(shift_id: str, body: ReopenIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return shift_out(services.shifts.reopen_shift(user.id, shift_id, body.reason))


@router.get("/shifts/{shift_id}/assignments", response_model=list[AssignmentOut])
def list_assignments(shift_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [assignment_out(a) for a in services.shifts.list_nozzle_assignments(user.id, shift_id)]


@router.post("/shifts/{shift_id}/assignments", response_model=AssignmentOut, status_code=201)
def assign_nozzle(shift_id: str, body: AssignIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return assignment_out(services.shifts.assign_nozzle(user.id, shift_id, NozzleAssignmentCreate(**body.model_dump())))


@router.post("/shift-assignments/{assignment_id}/complete", response_model=AssignmentOut)
def complete_assignment(
    assignment_id: str, body: CompleteIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return assignment_out(
        services.shifts.complete_nozzle_assignment(user.id, assignment_id, NozzleAssignmentComplete(**body.model_dump()))
    )


@router.post("/shift-assignments/{assignment_id}/cancel", response_model=AssignmentOut)
def cancel_assignment(
    assignment_id: str, body: CancelAssignmentIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return assignment_out(services.shifts.cancel_nozzle_assignment(user.id, assignment_id, body.reason))
