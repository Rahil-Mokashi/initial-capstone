from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.repositories.base import safe_commit


class AttendanceRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, attendance_id: str) -> Optional[Attendance]:
        return self._session.query(Attendance).filter_by(id=attendance_id).first()

    def get_by_employee_and_date(self, employee_id: str, attendance_date: date) -> Optional[Attendance]:
        return (
            self._session.query(Attendance)
            .filter_by(employee_id=employee_id, attendance_date=attendance_date)
            .first()
        )

    def list_for_employee(
        self, employee_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> List[Attendance]:
        query = self._session.query(Attendance).filter_by(employee_id=employee_id)
        if date_from:
            query = query.filter(Attendance.attendance_date >= date_from)
        if date_to:
            query = query.filter(Attendance.attendance_date <= date_to)
        return query.order_by(Attendance.attendance_date.desc()).all()

    def list_for_date(self, attendance_date: date) -> List[Attendance]:
        return self._session.query(Attendance).filter_by(attendance_date=attendance_date).all()

    def add(self, attendance: Attendance) -> Attendance:
        self._session.add(attendance)
        safe_commit(self._session)
        self._session.refresh(attendance)
        return attendance

    def update(self, attendance: Attendance) -> Attendance:
        safe_commit(self._session)
        self._session.refresh(attendance)
        return attendance
