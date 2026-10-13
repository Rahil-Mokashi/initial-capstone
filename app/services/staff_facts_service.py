"""Staff facts: what the records say about each employee over a period (LAN build, Phase 5). Owners and the accountant only.

Facts, not a verdict: attendance counts, overtime, cash shortages booked against the person (and what has been paid back), and
advances given. The rows are in employee-code order, never sorted by anything that reads as a score, and nothing is added up into a
rating. The shift-entry stand-in records (NOZZLE-N1 ...) are not people and are left out.
"""

from datetime import date
from decimal import Decimal
from typing import Dict, Optional

from app.core.constants import AttendanceStatus, Permission
from app.core.money import money
from app.core.permissions import require_permission
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.employee_cash_shortage import EmployeeCashShortage
from app.models.payroll import EmployeeAdvance
from app.services.report_service import TableReport
from app.services.shift_close_service import STAND_IN_PREFIX

_Z = Decimal("0")
HEADERS = ["Code", "Name", "Days present", "Late", "Half days", "Absent", "On leave", "Overtime (hours)", "Cash shortages", "Shortage amount", "Paid back", "Still owed", "Advances given"]
MONEY_COLUMNS = frozenset({9, 10, 11, 12})


class StaffFactsService:
    def __init__(self, session, auth_service):
        self._session = session
        self._auth_service = auth_service

    @require_permission(Permission.STAFF_FACTS_VIEW.value)
    def report(self, actor_user_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None) -> TableReport:
        employees = (
            self._session.query(Employee).order_by(Employee.employee_code).all()
        )
        employees = [e for e in employees if not (e.employee_code or "").startswith(STAND_IN_PREFIX)]
        attendance = self._attendance_by_employee(date_from, date_to)
        rows = []
        for e in employees:
            a = attendance.get(e.id, {})
            count, total, paid, owed = self._shortage_facts(e.id, date_from, date_to)
            advances = self._advances(e.id, date_from, date_to)
            if not (a or count or advances):
                continue  # nothing on record for this person in this period
            rows.append([
                e.employee_code, f"{e.first_name} {e.last_name}".strip(),
                str(a.get(AttendanceStatus.PRESENT.value, 0)), str(a.get(AttendanceStatus.LATE.value, 0)),
                str(a.get(AttendanceStatus.HALF_DAY.value, 0)), str(a.get(AttendanceStatus.ABSENT.value, 0)),
                str(a.get(AttendanceStatus.LEAVE.value, 0)), f"{Decimal(a.get('overtime', 0)) / 60:.1f}",
                str(count), f"{money(total)}", f"{money(paid)}", f"{money(owed)}", f"{money(advances)}",
            ])
        period = f"{date_from or 'the beginning'} to {date_to or 'today'}"
        return TableReport(
            title=f"Staff facts ({period}) - a record of what happened, not a score", headers=list(HEADERS), rows=rows,
            money_columns=MONEY_COLUMNS,
        )

    def _attendance_by_employee(self, date_from, date_to) -> Dict[str, dict]:
        query = self._session.query(Attendance)
        if date_from:
            query = query.filter(Attendance.attendance_date >= date_from)
        if date_to:
            query = query.filter(Attendance.attendance_date <= date_to)
        out: Dict[str, dict] = {}
        for rec in query.all():
            d = out.setdefault(rec.employee_id, {})
            d[rec.status] = d.get(rec.status, 0) + 1
            d["overtime"] = d.get("overtime", 0) + (rec.overtime_minutes or 0)
        return out

    def _shortage_facts(self, employee_id: str, date_from, date_to):
        query = self._session.query(EmployeeCashShortage).filter_by(employee_id=employee_id)
        rows = [s for s in query.all() if self._within(s.recorded_at, date_from, date_to)]
        total = sum((s.amount for s in rows), _Z)
        paid = sum((sum((r.amount for r in s.recoveries), _Z) for s in rows), _Z)
        return len(rows), total, paid, total - paid

    def _advances(self, employee_id: str, date_from, date_to) -> Decimal:
        query = self._session.query(EmployeeAdvance).filter_by(employee_id=employee_id, status="active")
        if date_from:
            query = query.filter(EmployeeAdvance.given_on >= date_from)
        if date_to:
            query = query.filter(EmployeeAdvance.given_on <= date_to)
        return sum((a.amount for a in query.all()), _Z)

    @staticmethod
    def _within(moment, date_from, date_to) -> bool:
        if moment is None:
            return True
        day = moment.astimezone().date() if getattr(moment, "tzinfo", None) else moment.date()
        return (date_from is None or day >= date_from) and (date_to is None or day <= date_to)
