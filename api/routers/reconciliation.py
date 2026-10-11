"""Shift reconciliation, the shift cash book (advance / final / bank deposits) and employee cash shortages.
Same ReconciliationService / ShiftCashBookService / EmployeeShortageService calls as
app/ui/reconciliation_window.py."""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, Out
from api.services import Services
from app.schemas.employee_cash_shortage import EmployeeCashShortageRecord, EmployeeShortageRecoveryRecord
from app.schemas.shift_cash_book import ShiftBankDepositRecord, ShiftCashBookRecord
from app.schemas.shift_reconciliation import ShiftReconciliationPerform

router = APIRouter(tags=["reconciliation"])


class LineOut(Out):
    tender: Optional[str] = None
    variance: MoneyOut


class ShiftReconciliationOut(Out):
    id: str
    shift_id: str
    shift: Optional[str] = None
    lines: list[LineOut]
    classification: str
    status: str
    remarks: Optional[str] = None


class ExpectedOut(Out):
    tender_id: str
    tender: str
    expected: MoneyOut


class CashBookOut(Out):
    shift_id: str
    shift: Optional[str] = None
    opening_balance: MoneyOut
    advance_amount: MoneyOut
    final_amount: MoneyOut
    bank_deposits_total: MoneyOut
    closing_cash_in_hand: MoneyOut
    recorded_by: Optional[str] = None


class ShortageOut(Out):
    id: str
    employee: Optional[str] = None
    shift: Optional[str] = None
    tender: Optional[str] = None
    amount: MoneyOut
    recovered: MoneyOut
    outstanding: MoneyOut
    status: str


class IdLabel(Out):
    id: str
    label: str


class ShortageOptions(Out):
    """Dropdowns for the shortage dialogs: lines not yet booked, and shortages that still owe money."""

    unbooked_lines: list[IdLabel]
    outstanding_shortages: list[IdLabel]


class PerformIn(In):
    shift_id: str
    declared_amounts: dict[str, MoneyIn]
    remarks: Optional[str] = None


class ApproveIn(In):
    remarks: str = ""


class MovementsIn(In):
    shift_id: str
    advance_amount: MoneyIn = "0"
    final_amount: MoneyIn = "0"


class DepositIn(In):
    shift_id: str
    bank_name: str
    amount: MoneyIn


class ShortageIn(In):
    shift_reconciliation_line_id: str
    employee_id: str
    notes: Optional[str] = None


class RecoveryIn(In):
    employee_cash_shortage_id: str
    shift_id: str
    amount: MoneyIn
    notes: Optional[str] = None


class DoneOut(Out):
    id: str


def _shift_label(shift) -> Optional[str]:
    return f"{shift.shift_date} {shift.shift_label}" if shift else None


def recon_out(r) -> ShiftReconciliationOut:
    return ShiftReconciliationOut(
        id=r.id,
        shift_id=r.shift_id,
        shift=_shift_label(r.shift),
        lines=[LineOut(tender=line.tender.name, variance=line.variance) for line in r.lines if line.tender],
        classification=r.classification,
        status=r.status,
        remarks=getattr(r, "remarks", None),
    )


# ---- reconciliation ---------------------------------------------------------------------
@router.get("/reconciliation", response_model=list[ShiftReconciliationOut])
def list_reconciliations(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [recon_out(r) for r in services.reconciliation.list_reconciliations(user.id)]


@router.get("/reconciliation/expected", response_model=list[ExpectedOut])
def expected_amounts(
    shift_id: str = Query(), user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    pairs = services.reconciliation.get_expected_amounts_for_shift(user.id, shift_id)
    return [ExpectedOut(tender_id=t.id, tender=t.name, expected=e) for t, e in sorted(pairs, key=lambda p: p[0].name)]


@router.post("/reconciliation", response_model=ShiftReconciliationOut, status_code=201)
def perform(body: PerformIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    data = ShiftReconciliationPerform(
        shift_id=body.shift_id,
        declared_amounts={k: Decimal(v) for k, v in body.declared_amounts.items()},
        remarks=body.remarks,
    )
    return recon_out(services.reconciliation.perform_shift_reconciliation(user.id, data))


@router.post("/reconciliation/{reconciliation_id}/approve", response_model=ShiftReconciliationOut)
def approve(reconciliation_id: str, body: ApproveIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return recon_out(services.reconciliation.approve_shift_reconciliation(user.id, reconciliation_id, body.remarks.strip()))


# ---- cash book ---------------------------------------------------------------------------
@router.get("/cash-book", response_model=list[CashBookOut])
def list_cash_books(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    out = []
    for cb in services.cash_book.list_all(user.id):
        # opening balance and closing cash are recomputed each time, never stored (as in Qt)
        s = services.cash_book.get_cash_book_summary(user.id, cb.shift_id)
        out.append(
            CashBookOut(
                shift_id=cb.shift_id,
                shift=_shift_label(cb.shift),
                opening_balance=s.opening_balance,
                advance_amount=cb.advance_amount,
                final_amount=cb.final_amount,
                bank_deposits_total=s.bank_deposits_total,
                closing_cash_in_hand=s.closing_cash_in_hand,
                recorded_by=cb.recorded_by.username if cb.recorded_by else None,
            )
        )
    return out


@router.post("/cash-book/movements", response_model=DoneOut, status_code=201)
def record_movements(body: MovementsIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    cb = services.cash_book.record_shift_cash_movements(user.id, ShiftCashBookRecord(**body.model_dump()))
    return DoneOut(id=cb.id)


@router.post("/cash-book/deposits", response_model=DoneOut, status_code=201)
def record_deposit(body: DepositIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    d = services.cash_book.record_bank_deposit(user.id, ShiftBankDepositRecord(**body.model_dump()))
    return DoneOut(id=d.id)


# ---- employee cash shortages ---------------------------------------------------------------
def _shortage_out(services: Services, user_id: str, s) -> ShortageOut:
    e = s.employee
    line = s.shift_reconciliation_line
    shift = line.shift_reconciliation.shift if line and line.shift_reconciliation else None
    outstanding = services.shortages.get_outstanding_balance(user_id, s.id)
    return ShortageOut(
        id=s.id,
        employee=f"{e.first_name} {e.last_name}" if e else None,
        shift=_shift_label(shift),
        tender=line.tender.name if line and line.tender else None,
        amount=s.amount,
        recovered=s.amount - outstanding,
        outstanding=outstanding,
        status="Recovered" if outstanding <= 0 else "Outstanding",
    )


@router.get("/shortages", response_model=list[ShortageOut])
def list_shortages(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [_shortage_out(services, user.id, s) for s in services.shortages.list_all(user.id)]


@router.get("/shortages/options", response_model=ShortageOptions)
def shortage_options(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    unbooked = []
    for line in services.shortages.list_unbooked_shortage_lines(user.id):
        shift = line.shift_reconciliation.shift if line.shift_reconciliation else None
        label = _shift_label(shift) or line.shift_reconciliation_id
        tender = line.tender.name if line.tender else ""
        unbooked.append(IdLabel(id=line.id, label=f"{label} - {tender} short {abs(line.variance):.2f}"))
    owing = []
    for s in services.shortages.list_all(user.id):
        outstanding = services.shortages.get_outstanding_balance(user.id, s.id)
        if outstanding <= 0:
            continue
        who = f"{s.employee.first_name} {s.employee.last_name}" if s.employee else s.employee_id
        owing.append(IdLabel(id=s.id, label=f"{who} - outstanding {outstanding:.2f}"))
    return ShortageOptions(unbooked_lines=unbooked, outstanding_shortages=owing)


@router.post("/shortages", response_model=ShortageOut, status_code=201)
def record_shortage(body: ShortageIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    s = services.shortages.record_shortage(user.id, EmployeeCashShortageRecord(**body.model_dump()))
    return _shortage_out(services, user.id, s)


@router.post("/shortages/recoveries", response_model=DoneOut, status_code=201)
def record_recovery(body: RecoveryIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    r = services.shortages.record_recovery(user.id, EmployeeShortageRecoveryRecord(**body.model_dump()))
    return DoneOut(id=r.id)
