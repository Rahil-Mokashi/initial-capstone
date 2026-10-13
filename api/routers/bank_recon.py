"""Bank statement reconciliation: accounts, statement import (preview first), matching and the day view.

Thin: parsing, matching and every rule live in app/services/bank_*.py. A statement file travels as base64 text
in JSON (no extra upload library, works offline).
"""

import base64
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyOut, OptionalReason, Out
from api.services import Services
from app.services.bank_parsing import Mapping
from app.services.bank_recon_service import ALL_MODES, MODE_LABELS

router = APIRouter(tags=["bank"])


class BankModeOut(Out):
    mode: str
    label: str


class BankAccountOut(Out):
    id: str
    name: str
    account_mask: Optional[str] = None
    modes: list[str]


class BankAccountIn(In):
    name: str
    account_mask: Optional[str] = None
    modes: list[str] = []


class BankModesIn(In):
    modes: list[str]


class BankMappingIn(In):
    date_col: str
    description_col: str
    debit_col: Optional[str] = None
    credit_col: Optional[str] = None
    amount_col: Optional[str] = None
    type_col: Optional[str] = None
    balance_col: Optional[str] = None
    reference_col: Optional[str] = None
    date_format: Optional[str] = None
    header_row: int = 0
    delimiter: Optional[str] = None
    sheet: Optional[str] = None


class BankProfileOut(Out):
    name: str
    mapping: dict


class BankFileIn(In):
    filename: str
    content_base64: str
    mapping: BankMappingIn
    skip_unreadable: bool = False


class BankStatementRowOut(Out):
    id: str
    bank_account_id: str
    txn_date: date
    description: str
    reference: Optional[str] = None
    debit: MoneyOut
    credit: MoneyOut
    balance: Optional[MoneyOut] = None
    match_id: Optional[str] = None
    match_status: Optional[str] = None
    match_kind: Optional[str] = None
    locked: bool = False


class BankHeadersIn(In):
    filename: str
    content_base64: str
    header_row: int = 0
    sheet: Optional[str] = None


class BankHeadersOut(Out):
    headers: list[str]
    first_rows: list[list[str]]


class BankPreviewOut(Out):
    headers: list[str]
    sample: list[BankStatementRowOut]
    row_count: int
    problems: list[dict]
    new_rows: int
    duplicate_rows: int
    opening_balance: Optional[MoneyOut] = None
    closing_balance: Optional[MoneyOut] = None
    breaks: list[dict]
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    same_file_before: bool


class BankImportOut(Out):
    id: str
    filename: str
    row_count: int
    new_rows: int
    duplicate_rows: int
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    opening_balance: Optional[MoneyOut] = None
    closing_balance: Optional[MoneyOut] = None
    continuity_ok: bool
    break_count: int
    continuity_notes: Optional[str] = None
    imported_at: datetime


class BankExpectedOut(Out):
    id: str
    mode: str
    label: str
    business_date: date
    win_to: date
    amount: MoneyOut
    reference: Optional[str] = None
    description: str
    match_id: Optional[str] = None
    match_status: Optional[str] = None
    locked: bool = False


class BankDayModeOut(Out):
    day: date
    mode: str
    label: str
    expected: MoneyOut
    received: MoneyOut
    charges: MoneyOut
    suggested: MoneyOut
    unmatched: MoneyOut
    status: str


class BankAgedOut(Out):
    expected: BankExpectedOut
    age_days: int


class BankExceptionsOut(Out):
    unmatched_credits: list[BankStatementRowOut]
    aged_expected: list[BankAgedOut]
    total_charges: MoneyOut
    suggestions: int
    broken_imports: list[BankImportOut]


class BankSuggestionOut(Out):
    match_id: str
    rule: str
    note: Optional[str] = None
    charges: MoneyOut
    expected: list[BankExpectedOut]
    rows: list[BankStatementRowOut]


class BankRunIn(In):
    date_from: date
    date_to: date


class BankRunOut(Out):
    auto: int
    suggested: int
    reversals: int


class BankManualIn(In):
    expected_ids: list[str]
    row_ids: list[str]
    reason: OptionalReason


class BankReasonBody(In):
    reason: OptionalReason


class BankLockIn(In):
    locked: bool = True


class BankMatchOut(Out):
    id: str
    status: str
    kind: str
    locked: bool


def _mapping(m: BankMappingIn) -> Mapping:
    return Mapping.from_json(m.model_dump())


def _row(r, row_state) -> BankStatementRowOut:
    m = row_state.get(r.id)
    return BankStatementRowOut(
        id=r.id, bank_account_id=r.bank_account_id, txn_date=r.txn_date, description=r.description, reference=r.reference,
        debit=r.debit, credit=r.credit, balance=r.balance, match_id=m.id if m else None, match_status=m.status if m else None,
        match_kind=m.kind if m else None, locked=bool(m and m.locked),
    )


def _exp(e, exp_state) -> BankExpectedOut:
    m = exp_state.get(e.id)
    return BankExpectedOut(
        id=e.id, mode=e.mode, label=MODE_LABELS.get(e.mode, e.mode), business_date=e.business_date, win_to=e.win_to, amount=e.amount,
        reference=e.reference, description=e.description, match_id=m.id if m else None, match_status=m.status if m else None,
        locked=bool(m and m.locked),
    )


def _imp(i) -> BankImportOut:
    return BankImportOut.model_validate(i)


@router.get("/bank/modes", response_model=list[BankModeOut])
def modes(user: CurrentUser = Depends(current_user)):
    return [BankModeOut(mode=m, label=MODE_LABELS.get(m, m)) for m in ALL_MODES]


@router.get("/bank/accounts", response_model=list[BankAccountOut])
def accounts(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [BankAccountOut(id=a.id, name=a.name, account_mask=a.account_mask, modes=sorted(m.mode for m in a.modes)) for a in services.bank.list_accounts(user.id)]


@router.post("/bank/accounts", response_model=BankAccountOut, status_code=201)
def create_account(body: BankAccountIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    a = services.bank.create_account(user.id, body.name, body.account_mask, body.modes)
    return BankAccountOut(id=a.id, name=a.name, account_mask=a.account_mask, modes=sorted(m.mode for m in a.modes))


@router.put("/bank/accounts/{account_id}/modes", response_model=BankAccountOut)
def set_modes(account_id: str, body: BankModesIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    a = services.bank.set_account_modes(user.id, account_id, body.modes)
    return BankAccountOut(id=a.id, name=a.name, account_mask=a.account_mask, modes=sorted(m.mode for m in a.modes))


@router.get("/bank/accounts/{account_id}/profiles", response_model=list[BankProfileOut])
def profiles(account_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    import json

    return [BankProfileOut(name=p.name, mapping=json.loads(p.mapping_json)) for p in services.bank.profiles(user.id, account_id)]


@router.put("/bank/accounts/{account_id}/profiles/{name}", response_model=BankProfileOut)
def save_profile(account_id: str, name: str, body: BankMappingIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    import json

    p = services.bank.save_profile(user.id, account_id, name, _mapping(body))
    return BankProfileOut(name=p.name, mapping=json.loads(p.mapping_json))


@router.post("/bank/accounts/{account_id}/headers", response_model=BankHeadersOut)
def file_headers(account_id: str, body: BankHeadersIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """The column names a statement file offers (from the header row the person points at), so the layout can be chosen."""
    headers, rows = services.bank.file_headers(user.id, body.filename, base64.b64decode(body.content_base64), body.header_row, body.sheet)
    return BankHeadersOut(headers=headers, first_rows=rows[:5])


@router.post("/bank/accounts/{account_id}/preview", response_model=BankPreviewOut)
def preview(account_id: str, body: BankFileIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    p = services.bank.preview_import(user.id, account_id, body.filename, base64.b64decode(body.content_base64), _mapping(body.mapping))
    return BankPreviewOut(
        headers=p.headers, sample=[BankStatementRowOut(id=str(r.line_no), bank_account_id=account_id, txn_date=r.txn_date, description=r.description,
                                                   reference=r.reference, debit=r.debit, credit=r.credit, balance=r.balance) for r in p.sample],
        row_count=p.row_count, problems=[{"line": ln, "message": msg} for ln, msg in p.problems], new_rows=p.new_rows,
        duplicate_rows=p.duplicate_rows, opening_balance=p.opening_balance, closing_balance=p.closing_balance,
        breaks=[{"line": ln, "gap": str(gap)} for ln, gap in p.breaks], date_from=p.date_from, date_to=p.date_to,
        same_file_before=p.same_file_before,
    )


@router.post("/bank/accounts/{account_id}/import", response_model=BankImportOut, status_code=201)
def import_statement(account_id: str, body: BankFileIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    rec = services.bank.import_statement(user.id, account_id, body.filename, base64.b64decode(body.content_base64), _mapping(body.mapping), body.skip_unreadable)
    return _imp(rec)


@router.get("/bank/accounts/{account_id}/imports", response_model=list[BankImportOut])
def imports(account_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [_imp(i) for i in services.bank.imports(user.id, account_id)]


@router.post("/bank/match/run", response_model=BankRunOut)
def run(body: BankRunIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BankRunOut(**services.bank.run_matching(user.id, body.date_from, body.date_to))


@router.get("/bank/days", response_model=list[BankDayModeOut])
def days(date_from: date, date_to: date, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [BankDayModeOut.model_validate(d, from_attributes=True) for d in services.bank.day_view(user.id, date_from, date_to)]


@router.get("/bank/exceptions", response_model=BankExceptionsOut)
def exceptions(date_from: date, date_to: date, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    ex = services.bank.exceptions(user.id, date_from, date_to)
    exp_state, row_state = services.bank.match_state()
    return BankExceptionsOut(
        unmatched_credits=[_row(r, row_state) for r in ex.unmatched_credits],
        aged_expected=[BankAgedOut(expected=_exp(e, exp_state), age_days=age) for e, age in ex.aged_expected],
        total_charges=ex.total_charges, suggestions=ex.suggestions, broken_imports=[_imp(i) for i in ex.broken_imports],
    )


@router.get("/bank/suggestions", response_model=list[BankSuggestionOut])
def suggestions(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    out = []
    for m in services.bank.suggestions(user.id):
        out.append(BankSuggestionOut(
            match_id=m.id, rule=m.rule, note=m.note, charges=m.charges,
            expected=[_exp(i.expected, {i.expected.id: m}) for i in m.items if i.expected_id],
            rows=[_row(i.row, {i.row.id: m}) for i in m.items if i.row_id],
        ))
    return out


@router.get("/bank/expected", response_model=list[BankExpectedOut])
def expected(date_from: date, date_to: date, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    exp_state, _ = services.bank.match_state()
    return [_exp(e, exp_state) for e in services.bank.expected(user.id, date_from, date_to)]


@router.get("/bank/rows", response_model=list[BankStatementRowOut])
def rows(date_from: date, date_to: date, account_id: Optional[str] = None, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    _, row_state = services.bank.match_state()
    return [_row(r, row_state) for r in services.bank.rows(user.id, date_from, date_to, account_id)]


@router.post("/bank/matches/{match_id}/confirm", response_model=BankMatchOut)
def confirm(match_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BankMatchOut.model_validate(services.bank.confirm(user.id, match_id), from_attributes=True)


@router.post("/bank/matches/{match_id}/reject", response_model=BankMatchOut)
def reject(match_id: str, body: BankReasonBody, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BankMatchOut.model_validate(services.bank.reject(user.id, match_id, body.reason), from_attributes=True)


@router.post("/bank/matches/{match_id}/unmatch", response_model=BankMatchOut)
def unmatch(match_id: str, body: BankReasonBody, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BankMatchOut.model_validate(services.bank.unmatch(user.id, match_id, body.reason), from_attributes=True)


@router.post("/bank/matches/{match_id}/lock", response_model=BankMatchOut)
def lock(match_id: str, body: BankLockIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BankMatchOut.model_validate(services.bank.lock(user.id, match_id, body.locked), from_attributes=True)


@router.post("/bank/matches/manual", response_model=BankMatchOut, status_code=201)
def manual(body: BankManualIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BankMatchOut.model_validate(services.bank.manual_match(user.id, body.expected_ids, body.row_ids, body.reason), from_attributes=True)


@router.post("/bank/rows/{row_id}/not-ours", response_model=BankMatchOut, status_code=201)
def not_ours(row_id: str, body: BankReasonBody, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BankMatchOut.model_validate(services.bank.mark_not_ours(user.id, row_id, body.reason), from_attributes=True)
