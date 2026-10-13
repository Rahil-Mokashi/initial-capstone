"""Payroll v1: salary setup, advances, the monthly register, owner approval, payment, payslips.

Rules are settings (U-04): the default is the brief's: monthly salary prorated by days present, with deductions typed
explicitly. Days come from the existing attendance records. A run goes draft -> approved (an OWNER, by name) -> paid;
nothing is paid before approval. Everything is audit-logged and nothing is deleted (voids carry a reason).
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import money
from app.core.permissions import require_permission
from app.models.payroll import EmployeeAdvance, PayrollLine, PayrollPayment, PayrollRun, SalarySetup
from app.repositories.base import session_for, unit_of_work
from app.services.report_service import TableReport

_Z = Decimal("0")
_HALF = Decimal("0.5")


@dataclass
class LineView:
    line: PayrollLine
    payment: Optional[PayrollPayment]
    advance_outstanding: Decimal
    shortage_outstanding: Decimal


@dataclass
class Register:
    run: PayrollRun
    lines: List[LineView]
    gross: Decimal = _Z
    advance: Decimal = _Z
    shortage: Decimal = _Z
    other: Decimal = _Z
    net: Decimal = _Z
    paid: Decimal = _Z


def month_bounds(month: str):
    try:
        y, m = (int(x) for x in month.split("-"))
        days = calendar.monthrange(y, m)[1]
    except (ValueError, calendar.IllegalMonthError):
        raise ValueError("Month must look like 2026-10") from None
    return date(y, m, 1), date(y, m, days), days


def paid_days(statuses: List[str], leave_paid: bool, holiday_paid: bool) -> Decimal:
    """Present and late days count 1, a half day 0.5; approved leave and holidays count only if the owner says so."""
    total = _Z
    for s in statuses:
        if s in ("present", "late"):
            total += 1
        elif s == "half_day":
            total += _HALF
        elif s == "leave" and leave_paid:
            total += 1
        elif s == "holiday" and holiday_paid:
            total += 1
    return total


class PayrollService:
    def __init__(self, repo, settings, audit_repo, auth_service):
        self._repo = repo
        self._settings = settings
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(repo)

    # -- salary and advances ---------------------------------------------------------------------------------------
    @require_permission(Permission.PAYROLL_MANAGE.value)
    def set_salary(self, actor_user_id: str, employee_id: str, monthly_salary: Decimal, effective_from: date, note: Optional[str] = None):
        if monthly_salary <= 0:
            raise ValueError("The monthly salary must be more than zero")
        with unit_of_work(self._session):
            emp = self._employee(employee_id)
            old = self._repo.salary_on(employee_id, effective_from)
            row = self._repo.add_salary(SalarySetup(
                employee_id=employee_id, monthly_salary=money(monthly_salary), effective_from=effective_from,
                note=(note or "").strip() or None, set_by_id=actor_user_id,
            ))
            self._audit_repo.record(
                event_type="salary_set", actor_id=actor_user_id, entity_type="SalarySetup", entity_id=row.id,
                description=f"{emp.first_name} {emp.last_name}: {row.monthly_salary} a month from {effective_from}"
                + (f" (was {old.monthly_salary})" if old else ""),
                old_value=str(old.monthly_salary) if old else None, new_value=str(row.monthly_salary),
            )
            return row

    @require_permission(Permission.PAYROLL_VIEW.value)
    def salary_table(self, actor_user_id: str, on: Optional[date] = None):
        on = on or date.today()
        out = []
        for e in self._repo.active_employees():
            s = self._repo.salary_on(e.id, on)
            out.append((e, s))
        return out

    @require_permission(Permission.PAYROLL_MANAGE.value)
    def record_advance(self, actor_user_id: str, employee_id: str, amount: Decimal, given_on: date, method: str, note: Optional[str]):
        if amount <= 0:
            raise ValueError("An advance must be more than zero")
        if method not in ("cash", "bank"):
            raise ValueError("An advance is given in cash or from the bank")
        with unit_of_work(self._session):
            emp = self._employee(employee_id)
            row = self._repo.add_advance(EmployeeAdvance(
                employee_id=employee_id, amount=money(amount), given_on=given_on, method=method,
                note=(note or "").strip() or None, given_by_id=actor_user_id, status="active",
            ))
            self._audit_repo.record(
                event_type="advance_given", actor_id=actor_user_id, entity_type="EmployeeAdvance", entity_id=row.id,
                description=f"Advance of {row.amount} to {emp.first_name} {emp.last_name} on {given_on} ({method})",
            )
            return row

    @require_permission(Permission.PAYROLL_MANAGE.value)
    def void_advance(self, actor_user_id: str, advance_id: str, reason: str):
        if not (reason or "").strip():
            raise ValueError("A reason is required to void an advance")
        with unit_of_work(self._session):
            a = self._repo.get_advance(advance_id)
            if a is None:
                raise NotFoundError("Advance not found")
            if a.status == "void":
                raise ConflictError("This advance is already void")
            if self.advance_outstanding(a.employee_id, date.today(), exclude_advance=a.id) < 0:
                raise ConflictError("Salary has already recovered more than this would leave: void the recovery first")
            a.status, a.void_reason, a.voided_at = "void", reason.strip(), datetime.now(timezone.utc)
            self._repo.save_advance(a)
            self._audit_repo.record(event_type="advance_voided", actor_id=actor_user_id, entity_type="EmployeeAdvance",
                                    entity_id=a.id, description=f"Advance of {a.amount} voided: {reason.strip()}")
            return a

    @require_permission(Permission.PAYROLL_VIEW.value)
    def advances(self, actor_user_id: str, employee_id: Optional[str] = None):
        return self._repo.advances(employee_id)

    def advance_given(self, employee_id: str, up_to: date, exclude_advance: Optional[str] = None) -> Decimal:
        return sum((a.amount for a in self._repo.advances(employee_id) if a.given_on <= up_to and a.id != exclude_advance), _Z)

    def advance_recovered(self, employee_id: str, before_month: Optional[str] = None) -> Decimal:
        lines = self._repo.lines_before_month(employee_id, before_month) if before_month else self._repo.all_lines_of_employee(employee_id)
        return sum((l.advance_deduction for l in lines), _Z)

    def advance_outstanding(self, employee_id: str, up_to: date, before_month: Optional[str] = None, exclude_advance: Optional[str] = None) -> Decimal:
        return self.advance_given(employee_id, up_to, exclude_advance) - self.advance_recovered(employee_id, before_month)

    def shortage_outstanding(self, employee_id: str, before_month: Optional[str] = None) -> Decimal:
        booked, recovered = self._repo.shortages_outstanding(employee_id)
        lines = self._repo.lines_before_month(employee_id, before_month) if before_month else self._repo.all_lines_of_employee(employee_id)
        return booked - recovered - sum((l.shortage_deduction for l in lines), _Z)

    # -- the monthly register ------------------------------------------------------------------------------------------
    @require_permission(Permission.PAYROLL_MANAGE.value)
    def prepare_month(self, actor_user_id: str, month: str) -> PayrollRun:
        first, last, calendar_days = month_bounds(month)
        if self._repo.run_for_month(month) is not None:
            raise ConflictError(f"{month} has already been prepared")
        leave = self._settings.get("payroll_leave_paid") == "on"
        holiday = self._settings.get("payroll_holiday_paid") == "on"
        days = 30 if self._settings.get("payroll_days_basis") == "30" else calendar_days
        with unit_of_work(self._session):
            run = self._repo.add_run(PayrollRun(
                month=month, status="draft", days_in_month=days, leave_paid="on" if leave else "off",
                holiday_paid="on" if holiday else "off", prepared_by_id=actor_user_id,
            ))
            made = 0
            for emp in self._repo.active_employees():
                setup = self._repo.salary_on(emp.id, last)
                if setup is None:
                    continue
                statuses = [a.status for a in self._repo.attendance_in_month(emp.id, first, last)]
                present = paid_days(statuses, False, False)
                paid = min(Decimal(days), paid_days(statuses, leave, holiday))
                gross = money(setup.monthly_salary * paid / Decimal(days))
                self._session.add(PayrollLine(
                    run_id=run.id, employee_id=emp.id, employee_name=f"{emp.first_name} {emp.last_name}".strip(),
                    monthly_salary=setup.monthly_salary, days_in_month=days, days_present=present, paid_days=paid,
                    gross=gross, advance_deduction=_Z, shortage_deduction=_Z, other_deduction=_Z, net=gross,
                ))
                made += 1
            self._session.flush()
            self._audit_repo.record(
                event_type="payroll_prepared", actor_id=actor_user_id, entity_type="PayrollRun", entity_id=run.id,
                description=f"Prepared {month}: {made} employee(s), {days} days, leave paid {run.leave_paid}, holidays paid {run.holiday_paid}",
            )
            return run

    @require_permission(Permission.PAYROLL_MANAGE.value)
    def set_deductions(
        self, actor_user_id: str, line_id: str, advance: Decimal, shortage: Decimal, other: Decimal, other_note: Optional[str],
    ) -> PayrollLine:
        advance, shortage, other = money(advance), money(shortage), money(other)
        if min(advance, shortage, other) < 0:
            raise ValueError("A deduction cannot be negative")
        with unit_of_work(self._session):
            line = self._line(line_id)
            if line.run.status != "draft":
                raise ConflictError("This month is already approved: its deductions can no longer change")
            _, last, _ = month_bounds(line.run.month)
            adv_left = self.advance_outstanding(line.employee_id, last, before_month=line.run.month)
            if advance > adv_left:
                raise ValueError(f"Only {adv_left} of advances is still to be recovered from {line.employee_name}")
            short_left = self.shortage_outstanding(line.employee_id, before_month=line.run.month)
            if shortage > max(_Z, short_left):
                raise ValueError(f"Only {max(_Z, short_left)} of cash shortage is still to be recovered from {line.employee_name}")
            if advance + shortage + other > line.gross:
                raise ValueError("The deductions are more than the salary earned this month")
            old = (line.advance_deduction, line.shortage_deduction, line.other_deduction)
            line.advance_deduction, line.shortage_deduction, line.other_deduction = advance, shortage, other
            line.other_note = (other_note or "").strip() or None
            line.net = line.gross - advance - shortage - other
            self._repo.save_line(line)
            self._audit_repo.record(
                event_type="payroll_deductions_set", actor_id=actor_user_id, entity_type="PayrollLine", entity_id=line.id,
                description=f"{line.employee_name} {line.run.month}: advance {advance}, shortage {shortage}, other {other}; net {line.net} (was {old})",
            )
            return line

    @require_permission(Permission.PAYROLL_APPROVE.value)
    def approve(self, actor_user_id: str, run_id: str) -> PayrollRun:
        with unit_of_work(self._session):
            run = self._run(run_id)
            if run.status != "draft":
                raise ConflictError("This month is already approved")
            if not run.lines:
                raise ValueError("There is nothing in this month to approve")
            run.status, run.approved_by_id, run.approved_at = "approved", actor_user_id, datetime.now(timezone.utc)
            self._repo.save_run(run)
            total = sum((l.net for l in run.lines), _Z)
            self._audit_repo.record(
                event_type="payroll_approved", actor_id=actor_user_id, entity_type="PayrollRun", entity_id=run.id,
                description=f"{run.month} approved: {len(run.lines)} employee(s), net {total}",
            )
            return run

    @require_permission(Permission.PAYROLL_MANAGE.value)
    def pay(
        self, actor_user_id: str, line_id: str, method: str, paid_on: date, bank_account_id: Optional[str] = None,
        reference: Optional[str] = None,
    ) -> PayrollPayment:
        if method not in ("cash", "bank"):
            raise ValueError("Pay in cash or from the bank")
        if method == "bank" and not bank_account_id:
            raise ValueError("Choose the bank account the salary was paid from")
        with unit_of_work(self._session):
            line = self._line(line_id)
            run = line.run
            if run.status == "draft":
                raise ConflictError("An owner has to approve the month before anyone is paid")
            if any(p for p in self._line_payments(line) ):
                raise ConflictError(f"{line.employee_name} is already marked paid for {run.month}")
            row = self._repo.add_payment(PayrollPayment(
                line_id=line.id, amount=line.net, method=method, bank_account_id=bank_account_id if method == "bank" else None,
                paid_on=paid_on, reference=(reference or "").strip() or None, paid_by_id=actor_user_id, status="active",
            ))
            if all(self._line_payments(l) for l in run.lines):
                run.status, run.paid_at = "paid", datetime.now(timezone.utc)
                self._repo.save_run(run)
            self._audit_repo.record(
                event_type="salary_paid", actor_id=actor_user_id, entity_type="PayrollPayment", entity_id=row.id,
                description=f"{line.employee_name} {run.month}: {row.amount} paid by {method}" + (f" ({row.reference})" if row.reference else ""),
            )
            return row

    @require_permission(Permission.PAYROLL_MANAGE.value)
    def void_payment(self, actor_user_id: str, payment_id: str, reason: str) -> PayrollPayment:
        if not (reason or "").strip():
            raise ValueError("A reason is required to undo a payment")
        with unit_of_work(self._session):
            pay = self._session.get(PayrollPayment, payment_id)
            if pay is None:
                raise NotFoundError("Payment not found")
            if pay.status == "void":
                raise ConflictError("This payment is already undone")
            pay.status, pay.void_reason, pay.voided_at = "void", reason.strip(), datetime.now(timezone.utc)
            self._repo.save_payment(pay)
            run = pay.line.run
            if run.status == "paid":
                run.status, run.paid_at = "approved", None
                self._repo.save_run(run)
            self._audit_repo.record(event_type="salary_payment_voided", actor_id=actor_user_id, entity_type="PayrollPayment",
                                    entity_id=pay.id, description=f"Payment of {pay.amount} undone: {reason.strip()}")
            return pay

    def _line_payments(self, line: PayrollLine):
        return [p for p in self._repo.payments_for_run(line.run_id) if p.line_id == line.id]

    @require_permission(Permission.PAYROLL_VIEW.value)
    def register(self, actor_user_id: str, month: str) -> Optional[Register]:
        return self.register_internal(month)

    def register_internal(self, month: str) -> Optional[Register]:
        run = self._repo.run_for_month(month)
        if run is None:
            return None
        pays = {p.line_id: p for p in self._repo.payments_for_run(run.id)}
        reg = Register(run=run, lines=[])
        for l in run.lines:
            reg.lines.append(LineView(
                l, pays.get(l.id), self.advance_outstanding(l.employee_id, month_bounds(month)[1], before_month=month),
                max(_Z, self.shortage_outstanding(l.employee_id, before_month=month)),
            ))
            reg.gross += l.gross
            reg.advance += l.advance_deduction
            reg.shortage += l.shortage_deduction
            reg.other += l.other_deduction
            reg.net += l.net
            if l.id in pays:
                reg.paid += pays[l.id].amount
        return reg

    @require_permission(Permission.PAYROLL_VIEW.value)
    def runs(self, actor_user_id: str) -> List[PayrollRun]:
        return self._repo.list_runs()

    # -- payslip ----------------------------------------------------------------------------------------------------------------
    @require_permission(Permission.PAYROLL_VIEW.value)
    def payslip(self, actor_user_id: str, line_id: str) -> TableReport:
        line = self._line(line_id)
        run = line.run
        pay = next(iter(self._line_payments(line)), None)
        rows = [
            ["Monthly salary", f"{line.monthly_salary:.2f}", ""],
            ["Days in the month", str(line.days_in_month), ""],
            ["Days paid for", f"{line.paid_days}", ""],
            ["Salary earned", "", f"{line.gross:.2f}"],
            ["Advance recovered", f"{line.advance_deduction:.2f}", ""],
            ["Cash shortage recovered", f"{line.shortage_deduction:.2f}", ""],
            [f"Other deduction{(' (' + line.other_note + ')') if line.other_note else ''}", f"{line.other_deduction:.2f}", ""],
            ["Net pay", "", f"{line.net:.2f}"],
            ["Paid", (f"{pay.method} on {pay.paid_on}" + (f", ref {pay.reference}" if pay and pay.reference else "")) if pay else "not yet paid", ""],
        ]
        return TableReport(title=f"Payslip - {line.employee_name} - {run.month}", headers=["Item", "Amount / detail", "Total"], rows=rows)

    # -- helpers ------------------------------------------------------------------------------------------------------------------
    def _employee(self, employee_id: str):
        for e in self._repo.active_employees():
            if e.id == employee_id:
                return e
        raise NotFoundError("Employee not found")

    def _run(self, run_id: str) -> PayrollRun:
        r = self._repo.get_run(run_id)
        if r is None:
            raise NotFoundError("Payroll month not found")
        return r

    def _line(self, line_id: str) -> PayrollLine:
        l = self._repo.get_line(line_id)
        if l is None:
            raise NotFoundError("Payroll line not found")
        return l
