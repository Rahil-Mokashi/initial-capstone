"""
Attendance service layer (problemstatement.md #9).

Marking attendance creates one immutable-by-default record per employee
per day; any change after that must go through correct_attendance, which
requires a reason and is both permission-checked and audit-logged with the
old and new values — attendance history is never silently overwritten.
"""

from datetime import date, datetime, timezone
from typing import List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.attendance import Attendance
from app.schemas.attendance import AttendanceCorrection, AttendanceMark


class AttendanceService:
    def __init__(self, attendance_repo, employee_repo, audit_repo, auth_service):
        self._attendance_repo = attendance_repo
        self._employee_repo = employee_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    @require_permission(Permission.ATTENDANCE_MANAGE.value)
    def mark_attendance(self, actor_user_id: str, data: AttendanceMark) -> Attendance:
        if not self._employee_repo.get_by_id(data.employee_id):
            raise NotFoundError(f"Employee not found: {data.employee_id}")

        if self._attendance_repo.get_by_employee_and_date(data.employee_id, data.attendance_date):
            raise ConflictError(
                f"Attendance for {data.employee_id} on {data.attendance_date} is already marked; "
                "use correct_attendance to change it"
            )

        attendance = Attendance(
            employee_id=data.employee_id,
            attendance_date=data.attendance_date,
            status=data.status.value,
            check_in_time=data.check_in_time,
            check_out_time=data.check_out_time,
            shift_label=data.shift_label,
            supervisor_id=data.supervisor_id,
            overtime_minutes=data.overtime_minutes,
        )
        attendance = self._attendance_repo.add(attendance)
        self._audit_repo.record(
            event_type="attendance_marked",
            actor_id=actor_user_id,
            entity_type="Attendance",
            entity_id=attendance.id,
            description=f"Marked {data.status.value} for employee {data.employee_id} on {data.attendance_date}",
        )
        return attendance

    @require_permission(Permission.ATTENDANCE_MANAGE.value)
    def correct_attendance(
        self, actor_user_id: str, attendance_id: str, data: AttendanceCorrection, reason: str
    ) -> Attendance:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to correct attendance")

        attendance = self._get_or_raise(attendance_id)
        old_snapshot = (
            f"status={attendance.status}, check_in={attendance.check_in_time}, "
            f"check_out={attendance.check_out_time}, overtime={attendance.overtime_minutes}"
        )

        for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
            if field == "status":
                value = value.value if hasattr(value, "value") else value
            setattr(attendance, field, value)

        attendance.correction_reason = reason.strip()
        attendance.corrected_by_id = actor_user_id
        attendance.corrected_at = datetime.now(timezone.utc)
        attendance = self._attendance_repo.update(attendance)

        new_snapshot = (
            f"status={attendance.status}, check_in={attendance.check_in_time}, "
            f"check_out={attendance.check_out_time}, overtime={attendance.overtime_minutes}"
        )
        self._audit_repo.record(
            event_type="attendance_corrected",
            actor_id=actor_user_id,
            entity_type="Attendance",
            entity_id=attendance.id,
            description=reason.strip(),
            old_value=old_snapshot,
            new_value=new_snapshot,
        )
        return attendance

    @require_permission(Permission.ATTENDANCE_VIEW.value)
    def get_attendance(self, actor_user_id: str, attendance_id: str) -> Attendance:
        return self._get_or_raise(attendance_id)

    @require_permission(Permission.ATTENDANCE_VIEW.value)
    def list_for_employee(
        self, actor_user_id: str, employee_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> List[Attendance]:
        return self._attendance_repo.list_for_employee(employee_id, date_from, date_to)

    @require_permission(Permission.ATTENDANCE_VIEW.value)
    def list_for_date(self, actor_user_id: str, attendance_date: date) -> List[Attendance]:
        return self._attendance_repo.list_for_date(attendance_date)

    def _get_or_raise(self, attendance_id: str) -> Attendance:
        attendance = self._attendance_repo.get_by_id(attendance_id)
        if not attendance:
            raise NotFoundError(f"Attendance record not found: {attendance_id}")
        return attendance
