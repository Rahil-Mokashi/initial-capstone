"""Repositories for payroll. Advances and payments are voided, never deleted."""

from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.payroll import EmployeeAdvance, PayrollLine, PayrollPayment, PayrollRun, SalarySetup
from app.repositories.base import safe_commit


class PayrollRepository:
    def __init__(self, session: Session):
        self._session = session

    def _add(self, row):
        self._session.add(row)
        safe_commit(self._session)
        self._session.refresh(row)
        return row

    def _save(self, row):
        safe_commit(self._session)
        self._session.refresh(row)
        return row

    # salary
    def add_salary(self, s: SalarySetup) -> SalarySetup:
        return self._add(s)

    def salary_on(self, employee_id: str, day: date) -> Optional[SalarySetup]:
        return (
            self._session.query(SalarySetup)
            .filter(SalarySetup.employee_id == employee_id, SalarySetup.effective_from <= day)
            .order_by(SalarySetup.effective_from.desc(), SalarySetup.created_at.desc())
            .first()
        )

    def salary_history(self, employee_id: str) -> List[SalarySetup]:
        return (
            self._session.query(SalarySetup).filter_by(employee_id=employee_id)
            .order_by(SalarySetup.effective_from.desc(), SalarySetup.created_at.desc()).all()
        )

    def employees_with_salary(self) -> List[str]:
        return [e for (e,) in self._session.query(SalarySetup.employee_id).distinct()]

    # advances
    def add_advance(self, a: EmployeeAdvance) -> EmployeeAdvance:
        return self._add(a)

    def save_advance(self, a: EmployeeAdvance) -> EmployeeAdvance:
        return self._save(a)

    def get_advance(self, advance_id: str) -> Optional[EmployeeAdvance]:
        return self._session.get(EmployeeAdvance, advance_id)

    def advances(self, employee_id: Optional[str] = None, include_void: bool = False) -> List[EmployeeAdvance]:
        q = self._session.query(EmployeeAdvance)
        if employee_id:
            q = q.filter_by(employee_id=employee_id)
        if not include_void:
            q = q.filter_by(status="active")
        return q.order_by(EmployeeAdvance.given_on, EmployeeAdvance.created_at).all()

    # runs and lines
    def add_run(self, r: PayrollRun) -> PayrollRun:
        return self._add(r)

    def save_run(self, r: PayrollRun) -> PayrollRun:
        return self._save(r)

    def run_for_month(self, month: str) -> Optional[PayrollRun]:
        return self._session.query(PayrollRun).filter_by(month=month).first()

    def get_run(self, run_id: str) -> Optional[PayrollRun]:
        return self._session.get(PayrollRun, run_id)

    def list_runs(self) -> List[PayrollRun]:
        return self._session.query(PayrollRun).order_by(PayrollRun.month.desc()).all()

    def get_line(self, line_id: str) -> Optional[PayrollLine]:
        return self._session.get(PayrollLine, line_id)

    def save_line(self, l: PayrollLine) -> PayrollLine:
        return self._save(l)

    def lines_before_month(self, employee_id: str, month: str) -> List[PayrollLine]:
        """Lines of EARLIER months' runs that are approved or paid: the deductions that have really been taken."""
        return (
            self._session.query(PayrollLine).join(PayrollRun, PayrollRun.id == PayrollLine.run_id)
            .filter(PayrollLine.employee_id == employee_id, PayrollRun.month < month, PayrollRun.status.in_(("approved", "paid")))
            .all()
        )

    def all_lines_of_employee(self, employee_id: str) -> List[PayrollLine]:
        return (
            self._session.query(PayrollLine).join(PayrollRun, PayrollRun.id == PayrollLine.run_id)
            .filter(PayrollLine.employee_id == employee_id, PayrollRun.status.in_(("approved", "paid"))).all()
        )

    # payments
    def add_payment(self, p: PayrollPayment) -> PayrollPayment:
        return self._add(p)

    def save_payment(self, p: PayrollPayment) -> PayrollPayment:
        return self._save(p)

    def payments_for_run(self, run_id: str) -> List[PayrollPayment]:
        return (
            self._session.query(PayrollPayment).join(PayrollLine, PayrollLine.id == PayrollPayment.line_id)
            .filter(PayrollLine.run_id == run_id, PayrollPayment.status == "active").all()
        )

    def payments_between(self, d_from: date, d_to: date) -> List[PayrollPayment]:
        return (
            self._session.query(PayrollPayment)
            .filter(PayrollPayment.paid_on >= d_from, PayrollPayment.paid_on <= d_to, PayrollPayment.status == "active").all()
        )

    # attendance and shortages (read-only, from the existing tables)
    def attendance_in_month(self, employee_id: str, first: date, last: date):
        from app.models.attendance import Attendance

        return (
            self._session.query(Attendance)
            .filter(Attendance.employee_id == employee_id, Attendance.attendance_date >= first, Attendance.attendance_date <= last,
                    Attendance.is_deleted.is_(False))
            .all()
        )

    def active_employees(self):
        from app.models.employee import Employee

        return self._session.query(Employee).filter(Employee.is_deleted.is_(False)).order_by(Employee.employee_code).all()

    def shortages_outstanding(self, employee_id: str):
        """(total booked, total recovered) from the existing cash shortage records."""
        from decimal import Decimal

        from app.models.employee_cash_shortage import EmployeeCashShortage

        rows = self._session.query(EmployeeCashShortage).filter_by(employee_id=employee_id).all()
        booked = sum((r.amount for r in rows), Decimal("0"))
        recovered = sum((rec.amount for r in rows for rec in r.recoveries), Decimal("0"))
        return booked, recovered
