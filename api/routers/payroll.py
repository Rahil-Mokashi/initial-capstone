"""Payroll: salary setup, advances, the monthly register, owner approval, payments and payslips.

Thin: every rule lives in app/services/payroll_service.py. Salaries are the accountant's to prepare and an owner's to approve.
"""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response

from api import reporting
from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out
from api.services import Services

router = APIRouter(tags=["payroll"])


class PayrollSalaryRowOut(Out):
    employee_id: str
    employee_code: str
    name: str
    monthly_salary: Optional[MoneyOut] = None
    effective_from: Optional[date] = None
    advance_outstanding: MoneyOut


class PayrollSalaryIn(In):
    monthly_salary: MoneyIn
    effective_from: date
    note: Optional[str] = None


class PayrollAdvanceIn(In):
    employee_id: str
    amount: MoneyIn
    given_on: date
    method: Literal["cash", "bank"] = "cash"
    note: Optional[str] = None


class PayrollAdvanceOut(Out):
    id: str
    employee_id: str
    employee: Optional[str] = None
    amount: MoneyOut
    given_on: date
    method: str
    note: Optional[str] = None


class PayrollVoidBody(In):
    reason: OptionalReason


class PayrollPrepareIn(In):
    month: str


class PayrollDeductionsIn(In):
    advance: MoneyIn = "0"
    shortage: MoneyIn = "0"
    other: MoneyIn = "0"
    other_note: Optional[str] = None


class PayrollPayIn(In):
    method: Literal["cash", "bank"]
    paid_on: date
    bank_account_id: Optional[str] = None
    reference: Optional[str] = None


class PayrollPaymentOut(Out):
    id: str
    amount: MoneyOut
    method: str
    paid_on: date
    reference: Optional[str] = None
    bank_account_id: Optional[str] = None


class PayrollLineOut(Out):
    id: str
    employee_id: str
    employee_name: str
    monthly_salary: MoneyOut
    days_in_month: int
    days_present: str
    paid_days: str
    gross: MoneyOut
    advance_deduction: MoneyOut
    shortage_deduction: MoneyOut
    other_deduction: MoneyOut
    other_note: Optional[str] = None
    net: MoneyOut
    payment: Optional[PayrollPaymentOut] = None
    advance_outstanding: MoneyOut
    shortage_outstanding: MoneyOut


class PayrollRegisterOut(Out):
    run_id: str
    month: str
    status: str
    days_in_month: int
    leave_paid: str
    holiday_paid: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    lines: list[PayrollLineOut]
    gross: MoneyOut
    advance: MoneyOut
    shortage: MoneyOut
    other: MoneyOut
    net: MoneyOut
    paid: MoneyOut


class PayrollRunRowOut(Out):
    id: str
    month: str
    status: str


class PayrollIdOut(Out):
    id: str


def _register(services: Services, user_id: str, month: str) -> Optional[PayrollRegisterOut]:
    reg = services.payroll.register(user_id, month)
    if reg is None:
        return None
    r = reg.run
    return PayrollRegisterOut(
        run_id=r.id, month=r.month, status=r.status, days_in_month=r.days_in_month, leave_paid=r.leave_paid,
        holiday_paid=r.holiday_paid, approved_by=r.approved_by.username if r.approved_by else None,
        approved_at=r.approved_at.isoformat() if r.approved_at else None,
        lines=[
            PayrollLineOut(
                id=v.line.id, employee_id=v.line.employee_id, employee_name=v.line.employee_name, monthly_salary=v.line.monthly_salary,
                days_in_month=v.line.days_in_month, days_present=str(v.line.days_present), paid_days=str(v.line.paid_days),
                gross=v.line.gross, advance_deduction=v.line.advance_deduction, shortage_deduction=v.line.shortage_deduction,
                other_deduction=v.line.other_deduction, other_note=v.line.other_note, net=v.line.net,
                payment=PayrollPaymentOut.model_validate(v.payment) if v.payment else None,
                advance_outstanding=v.advance_outstanding, shortage_outstanding=v.shortage_outstanding,
            ) for v in reg.lines
        ],
        gross=reg.gross, advance=reg.advance, shortage=reg.shortage, other=reg.other, net=reg.net, paid=reg.paid,
    )


@router.get("/payroll/salaries", response_model=list[PayrollSalaryRowOut])
def salaries(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [
        PayrollSalaryRowOut(
            employee_id=e.id, employee_code=e.employee_code, name=f"{e.first_name} {e.last_name}".strip(),
            monthly_salary=s.monthly_salary if s else None, effective_from=s.effective_from if s else None,
            advance_outstanding=services.payroll.advance_outstanding(e.id, date.today()),
        ) for e, s in services.payroll.salary_table(user.id)
    ]


@router.put("/payroll/salaries/{employee_id}", response_model=PayrollIdOut)
def set_salary(employee_id: str, body: PayrollSalaryIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return PayrollIdOut(id=services.payroll.set_salary(user.id, employee_id, body.monthly_salary, body.effective_from, body.note).id)


@router.get("/payroll/advances", response_model=list[PayrollAdvanceOut])
def advances(employee_id: Optional[str] = None, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [
        PayrollAdvanceOut(id=a.id, employee_id=a.employee_id, employee=f"{a.employee.first_name} {a.employee.last_name}" if a.employee else None,
                   amount=a.amount, given_on=a.given_on, method=a.method, note=a.note)
        for a in services.payroll.advances(user.id, employee_id)
    ]


@router.post("/payroll/advances", response_model=PayrollIdOut, status_code=201)
def give_advance(body: PayrollAdvanceIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return PayrollIdOut(id=services.payroll.record_advance(user.id, body.employee_id, body.amount, body.given_on, body.method, body.note).id)


@router.post("/payroll/advances/{advance_id}/void", response_model=PayrollIdOut)
def void_advance(advance_id: str, body: PayrollVoidBody, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return PayrollIdOut(id=services.payroll.void_advance(user.id, advance_id, body.reason).id)


@router.get("/payroll/runs", response_model=list[PayrollRunRowOut])
def runs(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [PayrollRunRowOut(id=r.id, month=r.month, status=r.status) for r in services.payroll.runs(user.id)]


@router.post("/payroll/runs", response_model=PayrollRegisterOut, status_code=201)
def prepare(body: PayrollPrepareIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.payroll.prepare_month(user.id, body.month)
    return _register(services, user.id, body.month)


@router.get("/payroll/register/{month}", response_model=Optional[PayrollRegisterOut])
def register(month: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _register(services, user.id, month)


@router.put("/payroll/lines/{line_id}/deductions", response_model=PayrollIdOut)
def deductions(line_id: str, body: PayrollDeductionsIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return PayrollIdOut(id=services.payroll.set_deductions(user.id, line_id, body.advance, body.shortage, body.other, body.other_note).id)


@router.post("/payroll/runs/{run_id}/approve", response_model=PayrollIdOut)
def approve(run_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return PayrollIdOut(id=services.payroll.approve(user.id, run_id).id)


@router.post("/payroll/lines/{line_id}/pay", response_model=PayrollPaymentOut, status_code=201)
def pay(line_id: str, body: PayrollPayIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return PayrollPaymentOut.model_validate(services.payroll.pay(user.id, line_id, body.method, body.paid_on, body.bank_account_id, body.reference))


@router.post("/payroll/payments/{payment_id}/void", response_model=PayrollIdOut)
def void_payment(payment_id: str, body: PayrollVoidBody, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return PayrollIdOut(id=services.payroll.void_payment(user.id, payment_id, body.reason).id)


@router.get("/payroll/lines/{line_id}/payslip", response_model=reporting.ReportView)
def payslip(line_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return reporting.view(services.payroll.payslip(user.id, line_id), services.settings.get_company_profile())


@router.get("/payroll/lines/{line_id}/payslip.{kind}")
def payslip_file(line_id: str, kind: Literal["pdf", "xlsx"], user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)) -> Response:
    return reporting.file_response(services.payroll.payslip(user.id, line_id), kind)
