"""Attendance and leave. Same AttendanceService / LeaveService calls as
app/ui/attendance_window.py and app/ui/leave_window.py."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, OptionalReason, Out
from api.services import Services
from app.core.constants import AttendanceStatus
from app.schemas.attendance import AttendanceCorrection, AttendanceMark
from app.schemas.leave_request import LeaveRequestCreate

router = APIRouter(tags=["attendance"])


class AttendanceOut(Out):
    id: str
    employee_id: str
    employee: Optional[str] = None
    attendance_date: date
    status: str
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    shift_id: Optional[str] = None
    shift_label: Optional[str] = None
    overtime_minutes: int
    correction_reason: Optional[str] = None
    corrected_at: Optional[datetime] = None


class LeaveOut(Out):
    id: str
    employee_id: str
    employee: Optional[str] = None
    date_from: date
    date_to: date
    reason: str
    status: str
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None


class MarkIn(In):
    employee_id: str
    attendance_date: date
    status: AttendanceStatus
    shift_id: Optional[str] = None
    shift_label: Optional[str] = None
    overtime_minutes: int = 0


class CorrectIn(In):
    status: Optional[AttendanceStatus] = None
    shift_id: Optional[str] = None
    overtime_minutes: Optional[int] = None
    reason: OptionalReason


class LeaveRequestIn(In):
    employee_id: str
    date_from: date
    date_to: date
    reason: OptionalReason


class ApproveIn(In):
    remarks: str = ""


class LeaveReasonIn(In):
    reason: OptionalReason


def attendance_out(a) -> AttendanceOut:
    e = a.employee
    return AttendanceOut(
        id=a.id,
        employee_id=a.employee_id,
        employee=f"{e.first_name} {e.last_name}" if e else None,
        attendance_date=a.attendance_date,
        status=a.status,
        check_in_time=a.check_in_time,
        check_out_time=a.check_out_time,
        shift_id=a.shift_id,
        shift_label=a.shift_label,
        overtime_minutes=a.overtime_minutes,
        correction_reason=a.correction_reason,
        corrected_at=a.corrected_at,
    )


def leave_out(r) -> LeaveOut:
    e = r.employee
    return LeaveOut(
        id=r.id,
        employee_id=r.employee_id,
        employee=f"{e.first_name} {e.last_name}" if e else None,
        date_from=r.date_from,
        date_to=r.date_to,
        reason=r.reason,
        status=r.status,
        decided_by=r.decided_by.username if r.decided_by else None,
        decision_reason=r.decision_reason,
    )


# ---- attendance ---------------------------------------------------------------------
@router.get("/attendance", response_model=list[AttendanceOut])
def list_attendance(
    on: date = Query(alias="date"), user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return [attendance_out(a) for a in services.attendance.list_for_date(user.id, on)]


@router.post("/attendance", response_model=AttendanceOut, status_code=201)
def mark_attendance(body: MarkIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return attendance_out(services.attendance.mark_attendance(user.id, AttendanceMark(**body.model_dump())))


@router.get("/attendance/{attendance_id}", response_model=AttendanceOut)
def get_attendance(attendance_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return attendance_out(services.attendance.get_attendance(user.id, attendance_id))


@router.post("/attendance/{attendance_id}/correct", response_model=AttendanceOut)
def correct_attendance(
    attendance_id: str, body: CorrectIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    data = AttendanceCorrection(**body.model_dump(exclude={"reason"}, exclude_unset=True))
    return attendance_out(services.attendance.correct_attendance(user.id, attendance_id, data, body.reason))


# ---- leave -------------------------------------------------------------------------
@router.get("/leave", response_model=list[LeaveOut])
def list_leave(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [leave_out(r) for r in services.leave.list_leave_requests(user.id)]


@router.post("/leave", response_model=LeaveOut, status_code=201)
def request_leave(body: LeaveRequestIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return leave_out(services.leave.request_leave(user.id, LeaveRequestCreate(**body.model_dump())))


@router.post("/leave/{leave_id}/approve", response_model=LeaveOut)
def approve_leave(leave_id: str, body: ApproveIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return leave_out(services.leave.approve_leave_request(user.id, leave_id, body.remarks.strip()))


@router.post("/leave/{leave_id}/reject", response_model=LeaveOut)
def reject_leave(leave_id: str, body: LeaveReasonIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return leave_out(services.leave.reject_leave_request(user.id, leave_id, body.reason))


@router.post("/leave/{leave_id}/cancel", response_model=LeaveOut)
def cancel_leave(leave_id: str, body: LeaveReasonIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return leave_out(services.leave.cancel_leave_request(user.id, leave_id, body.reason))
