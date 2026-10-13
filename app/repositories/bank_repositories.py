"""Repositories for bank reconciliation. Statement rows have no update or delete method on purpose."""

from datetime import date
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.bank import (
    BankAccount,
    BankAccountMode,
    BankImportProfile,
    BankMatch,
    BankMatchItem,
    BankStatementImport,
    BankStatementRow,
    ExpectedReceipt,
)
from app.repositories.base import safe_commit


class BankRepository:
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

    # accounts and modes
    def add_account(self, a: BankAccount) -> BankAccount:
        return self._add(a)

    def save_account(self, a: BankAccount) -> BankAccount:
        return self._save(a)

    def get_account(self, account_id: str) -> Optional[BankAccount]:
        return self._session.query(BankAccount).filter_by(id=account_id, is_deleted=False).first()

    def account_by_name(self, name: str) -> Optional[BankAccount]:
        return self._session.query(BankAccount).filter_by(name=name, is_deleted=False).first()

    def list_accounts(self) -> List[BankAccount]:
        return self._session.query(BankAccount).filter_by(is_deleted=False).order_by(BankAccount.name).all()

    def accounts_for_mode(self, mode: str) -> List[BankAccount]:
        return [a for a in self.list_accounts() if any(m.mode == mode for m in a.modes)]

    def set_modes(self, account: BankAccount, modes: List[str]) -> None:
        wanted = set(modes)
        for m in list(account.modes):
            if m.mode not in wanted:
                account.modes.remove(m)
        have = {m.mode for m in account.modes}
        for mode in sorted(wanted - have):
            account.modes.append(BankAccountMode(mode=mode))
        safe_commit(self._session)

    # import profiles
    def add_profile(self, p: BankImportProfile) -> BankImportProfile:
        return self._add(p)

    def save_profile(self, p: BankImportProfile) -> BankImportProfile:
        return self._save(p)

    def profile_by_name(self, account_id: str, name: str) -> Optional[BankImportProfile]:
        return self._session.query(BankImportProfile).filter_by(bank_account_id=account_id, name=name).first()

    def profiles(self, account_id: str) -> List[BankImportProfile]:
        return self._session.query(BankImportProfile).filter_by(bank_account_id=account_id).order_by(BankImportProfile.name).all()

    # imports and rows
    def add_import(self, i: BankStatementImport) -> BankStatementImport:
        return self._add(i)

    def imports_for_account(self, account_id: str) -> List[BankStatementImport]:
        return (
            self._session.query(BankStatementImport).filter_by(bank_account_id=account_id)
            .order_by(BankStatementImport.imported_at.desc()).all()
        )

    def import_by_file_hash(self, account_id: str, file_sha256: str) -> Optional[BankStatementImport]:
        return self._session.query(BankStatementImport).filter_by(bank_account_id=account_id, file_sha256=file_sha256).first()

    def existing_hashes(self, account_id: str) -> Set[str]:
        return {h for (h,) in self._session.query(BankStatementRow.row_hash).filter_by(bank_account_id=account_id)}

    def add_rows(self, rows: List[BankStatementRow]) -> None:
        self._session.add_all(rows)
        safe_commit(self._session)

    def get_row(self, row_id: str) -> Optional[BankStatementRow]:
        return self._session.get(BankStatementRow, row_id)

    def rows_between(self, d_from: date, d_to: date, account_id: Optional[str] = None) -> List[BankStatementRow]:
        q = self._session.query(BankStatementRow).filter(BankStatementRow.txn_date >= d_from, BankStatementRow.txn_date <= d_to)
        if account_id:
            q = q.filter_by(bank_account_id=account_id)
        return q.order_by(BankStatementRow.txn_date, BankStatementRow.line_no).all()

    def rows_by_ids(self, ids: List[str]) -> List[BankStatementRow]:
        if not ids:
            return []
        return self._session.query(BankStatementRow).filter(BankStatementRow.id.in_(ids)).all()

    # expected receipts
    def expected_by_key(self, key: str) -> Optional[ExpectedReceipt]:
        return self._session.query(ExpectedReceipt).filter_by(source_key=key).first()

    def add_expected(self, e: ExpectedReceipt) -> ExpectedReceipt:
        return self._add(e)

    def save_expected(self, e: ExpectedReceipt) -> ExpectedReceipt:
        return self._save(e)

    def get_expected(self, expected_id: str) -> Optional[ExpectedReceipt]:
        return self._session.get(ExpectedReceipt, expected_id)

    def expected_between(self, d_from: date, d_to: date, include_void: bool = False) -> List[ExpectedReceipt]:
        q = self._session.query(ExpectedReceipt).filter(ExpectedReceipt.business_date >= d_from, ExpectedReceipt.business_date <= d_to)
        if not include_void:
            q = q.filter_by(status="active")
        return q.order_by(ExpectedReceipt.business_date, ExpectedReceipt.mode, ExpectedReceipt.source_key).all()

    def expected_by_ids(self, ids: List[str]) -> List[ExpectedReceipt]:
        if not ids:
            return []
        return self._session.query(ExpectedReceipt).filter(ExpectedReceipt.id.in_(ids)).all()

    def active_expected_with_keys(self, prefix: str) -> List[ExpectedReceipt]:
        return self._session.query(ExpectedReceipt).filter(ExpectedReceipt.source_key.like(prefix + "%"), ExpectedReceipt.status == "active").all()

    # matches
    def add_match(self, m: BankMatch) -> BankMatch:
        return self._add(m)

    def save_match(self, m: BankMatch) -> BankMatch:
        return self._save(m)

    def get_match(self, match_id: str) -> Optional[BankMatch]:
        return self._session.get(BankMatch, match_id)

    def live_matches(self) -> List[BankMatch]:
        return self._session.query(BankMatch).filter(BankMatch.status != "void").all()

    def claimed_ids(self, statuses=("suggested", "confirmed")):
        """(expected ids, row ids) already in a live match of those statuses."""
        exp: Dict[str, str] = {}
        rows: Dict[str, str] = {}
        q = (
            self._session.query(BankMatchItem, BankMatch)
            .join(BankMatch, BankMatch.id == BankMatchItem.match_id)
            .filter(BankMatch.status.in_(statuses))
        )
        for item, match in q.all():
            if item.expected_id:
                exp[item.expected_id] = match.id
            if item.row_id:
                rows[item.row_id] = match.id
        return exp, rows

    def matches_for_expected(self, expected_ids: List[str]) -> List[BankMatch]:
        if not expected_ids:
            return []
        ids = {i for (i,) in self._session.query(BankMatchItem.match_id).filter(BankMatchItem.expected_id.in_(expected_ids))}
        return self._session.query(BankMatch).filter(BankMatch.id.in_(ids), BankMatch.status != "void").all() if ids else []

    def pending_suggestions(self) -> List[BankMatch]:
        return self._session.query(BankMatch).filter_by(status="suggested").order_by(BankMatch.created_at).all()

    def confirmed_matches(self) -> List[BankMatch]:
        return self._session.query(BankMatch).filter_by(status="confirmed").all()

    # --- reads across the books that feed the expected receipts ------------------------------------------------
    def tender_entries_between(self, d_from: date, d_to: date):
        from app.models.shift import Shift
        from app.models.shift_tender_entry import ShiftTenderEntry

        return (
            self._session.query(ShiftTenderEntry, Shift)
            .join(Shift, Shift.id == ShiftTenderEntry.shift_id)
            .filter(ShiftTenderEntry.voided_at.is_(None), Shift.shift_date >= d_from, Shift.shift_date <= d_to)
            .all()
        )

    def deposits_between(self, d_from: date, d_to: date):
        from app.models.shift import Shift
        from app.models.shift_bank_deposit import ShiftBankDeposit
        from app.models.shift_cash_book import ShiftCashBook

        return (
            self._session.query(ShiftBankDeposit, Shift)
            .join(ShiftCashBook, ShiftCashBook.id == ShiftBankDeposit.shift_cash_book_id)
            .join(Shift, Shift.id == ShiftCashBook.shift_id)
            .filter(Shift.shift_date >= d_from, Shift.shift_date <= d_to)
            .all()
        )

    def customer_payments_between(self, d_from: date, d_to: date):
        from app.models.customer_payment import CustomerPayment

        return (
            self._session.query(CustomerPayment)
            .filter(CustomerPayment.payment_date >= d_from, CustomerPayment.payment_date <= d_to)
            .all()
        )

    def payroll_payments_between(self, d_from: date, d_to: date):
        from app.models.payroll import PayrollPayment

        return (
            self._session.query(PayrollPayment)
            .filter(PayrollPayment.paid_on >= d_from, PayrollPayment.paid_on <= d_to, PayrollPayment.status == "active")
            .all()
        )
