"""Bank statement reconciliation: import, expected receipts from the app's own data, matching, and the day view.

Everything a person does here is audit-logged (import, match, unmatch, lock, not-ours). A confirmed match an
owner has locked cannot be undone by anyone else. Nothing is forced: a bank credit that cannot be tied to the
pump stays unmatched or is marked "not ours" with a reason (the goodwill business shares the office).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import money
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.models.bank import (
    BankAccount,
    BankImportProfile,
    BankMatch,
    BankMatchItem,
    BankStatementImport,
    BankStatementRow,
    ExpectedReceipt,
)
from app.repositories.base import session_for, unit_of_work
from app.services.bank_matching import Expected, Line, find_reversals, propose, window_for
from app.services.bank_parsing import Mapping, ParsedRow, check_continuity, parse_rows, read_table, row_hash

_Z = Decimal("0")
CASH_DEPOSIT = "cash_deposit"
CREDIT_RECEIPTS = "credit_receipts"
PAYROLL = "payroll"
ALL_MODES = ["Paytm", "PhonePe", "DTP Card", "Card", "Other", CASH_DEPOSIT, CREDIT_RECEIPTS, PAYROLL]
MODE_LABELS = {"Paytm": "PTM", "PhonePe": "PHONE PAY", "DTP Card": "DTP Card", "Card": "CARD", "Other": "Other",
               CASH_DEPOSIT: "Cash deposits", CREDIT_RECEIPTS: "Credit customers paying", PAYROLL: "Salaries"}


@dataclass
class ImportPreview:
    headers: List[str]
    sample: List[ParsedRow]
    row_count: int
    problems: List[tuple]  # (line_no, message)
    new_rows: int
    duplicate_rows: int
    opening_balance: Optional[Decimal]
    closing_balance: Optional[Decimal]
    breaks: List[tuple]  # (line_no, gap)
    date_from: Optional[date]
    date_to: Optional[date]
    same_file_before: bool


@dataclass
class DayMode:
    day: date
    mode: str
    label: str
    expected: Decimal = _Z
    received: Decimal = _Z
    charges: Decimal = _Z
    suggested: Decimal = _Z
    unmatched: Decimal = _Z
    awaiting: bool = False  # unmatched but still inside its date window
    status: str = "matched"  # matched | suggested | awaiting | unmatched


@dataclass
class Exceptions:
    unmatched_credits: List[BankStatementRow] = field(default_factory=list)
    aged_expected: List[tuple] = field(default_factory=list)  # (ExpectedReceipt, age_days)
    total_charges: Decimal = _Z
    suggestions: int = 0
    broken_imports: List[BankStatementImport] = field(default_factory=list)


class BankReconService:
    def __init__(self, repo, settings, audit_repo, auth_service):
        self._repo = repo
        self._settings = settings
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(repo)

    # -- accounts (H-02: which mode lands in which account is a setting per account) -------------------------------
    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def create_account(self, actor_user_id: str, name: str, mask: Optional[str], modes: List[str]) -> BankAccount:
        name = (name or "").strip()
        if not name:
            raise ValueError("Give the bank account a name")
        if self._repo.account_by_name(name):
            raise ConflictError(f"A bank account called {name!r} already exists")
        self._check_modes(modes)
        with unit_of_work(self._session):
            account = self._repo.add_account(BankAccount(name=name, account_mask=(mask or "").strip() or None, status=StatusEnum.ACTIVE.value))
            self._repo.set_modes(account, modes)
            self._audit_repo.record(
                event_type="bank_account_created", actor_id=actor_user_id, entity_type="BankAccount", entity_id=account.id,
                description=f"Bank account {name} ({account.account_mask or 'no number shown'}); takes: {', '.join(modes) or 'nothing yet'}",
            )
            return account

    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def set_account_modes(self, actor_user_id: str, account_id: str, modes: List[str]) -> BankAccount:
        self._check_modes(modes)
        with unit_of_work(self._session):
            account = self._account(account_id)
            before = sorted(m.mode for m in account.modes)
            self._repo.set_modes(account, modes)
            self._audit_repo.record(
                event_type="bank_account_modes_changed", actor_id=actor_user_id, entity_type="BankAccount", entity_id=account.id,
                description=f"{account.name}: takes {sorted(modes)} (was {before})",
            )
            return account

    @staticmethod
    def _check_modes(modes: List[str]) -> None:
        bad = [m for m in modes if m not in ALL_MODES]
        if bad:
            raise ValueError(f"Unknown payment mode: {', '.join(bad)}")

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def list_accounts(self, actor_user_id: str) -> List[BankAccount]:
        return self._repo.list_accounts()

    def _account(self, account_id: str) -> BankAccount:
        a = self._repo.get_account(account_id)
        if a is None:
            raise NotFoundError(f"Bank account not found: {account_id}")
        return a

    # -- import profiles and statement import ---------------------------------------------------------------------------
    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def save_profile(self, actor_user_id: str, account_id: str, name: str, mapping: Mapping) -> BankImportProfile:
        name = (name or "").strip()
        if not name:
            raise ValueError("Give the column layout a name")
        self._account(account_id)
        with unit_of_work(self._session):
            existing = self._repo.profile_by_name(account_id, name)
            payload = json.dumps(mapping.to_json(), sort_keys=True)
            if existing is None:
                row = self._repo.add_profile(BankImportProfile(bank_account_id=account_id, name=name, mapping_json=payload, created_by_id=actor_user_id))
            else:
                existing.mapping_json = payload
                row = self._repo.save_profile(existing)
            self._audit_repo.record(
                event_type="bank_import_profile_saved", actor_id=actor_user_id, entity_type="BankImportProfile", entity_id=row.id,
                description=f"Column layout '{name}' saved for account {account_id}",
            )
            return row

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def profiles(self, actor_user_id: str, account_id: str) -> List[BankImportProfile]:
        return self._repo.profiles(account_id)

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def file_headers(self, actor_user_id: str, filename: str, content: bytes, header_row: int = 0, sheet: Optional[str] = None):
        return read_table(filename, content, Mapping(date_col="", description_col="", header_row=header_row, sheet=sheet))

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def preview_import(self, actor_user_id: str, account_id: str, filename: str, content: bytes, mapping: Mapping) -> ImportPreview:
        """What importing this file would do. Stores nothing."""
        self._account(account_id)
        return self._preview(account_id, filename, content, mapping)[0]

    def _preview(self, account_id: str, filename: str, content: bytes, mapping: Mapping):
        headers, rows = read_table(filename, content, mapping)
        parsed, problems = parse_rows(headers, rows, mapping)
        have = self._repo.existing_hashes(account_id)
        seen = set()
        new, dup = [], 0
        for r in parsed:
            h = row_hash(account_id, r)
            if h in have or h in seen:
                dup += 1
            else:
                new.append((r, h))
            seen.add(h)
        opening, closing, breaks = check_continuity(parsed)
        file_hash = hashlib.sha256(content).hexdigest()
        preview = ImportPreview(
            headers=headers, sample=parsed[:15], row_count=len(parsed), problems=[(p.line_no, p.message) for p in problems],
            new_rows=len(new), duplicate_rows=dup, opening_balance=opening, closing_balance=closing,
            breaks=[(b.line_no, b.gap) for b in breaks],
            date_from=min((r.txn_date for r in parsed), default=None), date_to=max((r.txn_date for r in parsed), default=None),
            same_file_before=self._repo.import_by_file_hash(account_id, file_hash) is not None,
        )
        return preview, parsed, new, file_hash

    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def import_statement(
        self, actor_user_id: str, account_id: str, filename: str, content: bytes, mapping: Mapping, skip_unreadable: bool = False,
    ) -> BankStatementImport:
        self._account(account_id)
        preview, parsed, new, file_hash = self._preview(account_id, filename, content, mapping)
        if preview.problems and not skip_unreadable:
            first = preview.problems[0]
            raise ValueError(
                f"{len(preview.problems)} line(s) of the file cannot be read (first: line {first[0]}: {first[1]}). "
                "Fix the file or the column layout, or choose to skip them knowingly."
            )
        if not parsed:
            raise ValueError("The file has no readable rows")
        with unit_of_work(self._session):
            notes = []
            if preview.breaks:
                notes.append(f"{len(preview.breaks)} place(s) where the running balance jumps, so rows are missing: "
                             + ", ".join(f"line {ln} ({gap:+})" for ln, gap in preview.breaks[:10]))
            if preview.problems:
                notes.append(f"{len(preview.problems)} unreadable line(s) were skipped on purpose")
            rec = self._repo.add_import(BankStatementImport(
                bank_account_id=account_id, filename=filename, file_sha256=file_hash, imported_by_id=actor_user_id,
                row_count=len(parsed), new_rows=len(new), duplicate_rows=preview.duplicate_rows,
                date_from=preview.date_from, date_to=preview.date_to, opening_balance=preview.opening_balance,
                closing_balance=preview.closing_balance, continuity_ok=not preview.breaks, break_count=len(preview.breaks),
                continuity_notes="; ".join(notes) or None,
            ))
            self._repo.add_rows([
                BankStatementRow(
                    import_id=rec.id, bank_account_id=account_id, line_no=r.line_no, txn_date=r.txn_date, description=r.description,
                    reference=r.reference, debit=r.debit, credit=r.credit, balance=r.balance, row_hash=h,
                    raw_json=json.dumps(r.raw, ensure_ascii=False),
                ) for r, h in new
            ])
            self._audit_repo.record(
                event_type="bank_statement_imported", actor_id=actor_user_id, entity_type="BankStatementImport", entity_id=rec.id,
                description=f"{filename}: {len(new)} new row(s), {preview.duplicate_rows} already there"
                + (f"; {'; '.join(notes)}" if notes else ""),
            )
            return rec

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def imports(self, actor_user_id: str, account_id: str) -> List[BankStatementImport]:
        return self._repo.imports_for_account(account_id)

    # -- expected receipts, generated from the app's own data --------------------------------------------------------------
    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def sync_expected(self, actor_user_id: str, d_from: date, d_to: date) -> dict:
        return self.sync_expected_internal(actor_user_id, d_from, d_to)

    def sync_expected_internal(self, actor_user_id: Optional[str], d_from: date, d_to: date) -> dict:
        window = int(self._settings.get_decimal("bank_date_window_days"))
        wanted: Dict[str, dict] = {}
        for entry, shift in self._repo.tender_entries_between(d_from, d_to):
            wanted[f"shift_mode:{shift.id}:{entry.tender_id}"] = dict(
                source_type="shift_mode", source_id=entry.id, mode=entry.tender.name, business_date=shift.shift_date,
                amount=entry.amount, reference=entry.reference,
                description=f"{MODE_LABELS.get(entry.tender.name, entry.tender.name)} for {shift.shift_date:%d-%m-%Y} {shift.shift_label}",
                account_id=None,
            )
        for dep, shift in self._repo.deposits_between(d_from, d_to):
            acct = self._repo.account_by_name(dep.bank_name)
            wanted[f"cash_deposit:{dep.id}"] = dict(
                source_type="cash_deposit", source_id=dep.id, mode=CASH_DEPOSIT, business_date=shift.shift_date, amount=dep.amount,
                reference=None, description=f"Cash deposit to {dep.bank_name} ({shift.shift_date:%d-%m-%Y} {shift.shift_label})",
                account_id=acct.id if acct else None,
            )
        for p in self._repo.customer_payments_between(d_from, d_to):
            if p.payment_method == "cash":
                continue  # customers' cash reaches the bank through the cash deposits
            wanted[f"credit_payment:{p.id}"] = dict(
                source_type="credit_payment", source_id=p.id, mode=CREDIT_RECEIPTS, business_date=p.payment_date, amount=p.amount,
                reference=p.reference, description=f"{p.payment_method.upper()} payment from {p.customer.name if p.customer else 'customer'}",
                account_id=None,
            )
        for p in self._repo.payroll_payments_between(d_from, d_to):
            if p.method == "bank":
                wanted[f"payroll:{p.id}"] = dict(
                    source_type="payroll", source_id=p.id, mode=PAYROLL, business_date=p.paid_on, amount=p.amount, direction="debit",
                    reference=p.reference, account_id=p.bank_account_id,
                    description=f"Salary {p.line.employee_name} {p.line.run.month}",
                )
        created = updated = voided = 0
        for key, w in wanted.items():
            a, b = window_for(w["business_date"], window)
            row = self._repo.expected_by_key(key)
            if row is None:
                self._repo.add_expected(ExpectedReceipt(
                    source_key=key, source_type=w["source_type"], source_id=w["source_id"], direction=w.get("direction", "credit"), mode=w["mode"],
                    business_date=w["business_date"], win_from=a, win_to=b, amount=money(w["amount"]), reference=w["reference"],
                    description=w["description"], bank_account_id=w["account_id"], status="active",
                ))
                created += 1
            else:
                changed = row.status != "active" or row.amount != money(w["amount"]) or row.reference != w["reference"]
                if changed:
                    old = row.amount
                    row.amount, row.reference, row.status = money(w["amount"]), w["reference"], "active"
                    row.updated_at = datetime.now(timezone.utc)
                    self._repo.save_expected(row)
                    updated += 1
                    self._audit_repo.record(
                        event_type="bank_expected_changed", actor_id=actor_user_id, entity_type="ExpectedReceipt", entity_id=row.id,
                        description=f"{row.description}: expected {old} -> {row.amount}",
                    )
        for row in self._repo.expected_between(d_from, d_to):
            if row.source_type in ("shift_mode", "cash_deposit", "credit_payment", "payroll") and row.source_key not in wanted:
                row.status = "void"
                row.updated_at = datetime.now(timezone.utc)
                self._repo.save_expected(row)
                voided += 1
                self._audit_repo.record(
                    event_type="bank_expected_voided", actor_id=actor_user_id, entity_type="ExpectedReceipt", entity_id=row.id,
                    description=f"{row.description}: the record behind it was withdrawn",
                )
        return {"created": created, "updated": updated, "voided": voided}

    # -- matching -----------------------------------------------------------------------------------------------------------------
    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def run_matching(self, actor_user_id: str, d_from: date, d_to: date) -> dict:
        with unit_of_work(self._session):
            self.sync_expected_internal(actor_user_id, d_from, d_to)
            fee = self._settings.get_decimal("bank_fee_tolerance_percent")
            window = int(self._settings.get_decimal("bank_date_window_days"))
            claimed_e, claimed_r = self._repo.claimed_ids()
            rows_all = self._repo.rows_between(d_from, window_for(d_to, window)[1])
            reversal_count = self._pair_reversals(actor_user_id, rows_all, claimed_r)
            claimed_e, claimed_r = self._repo.claimed_ids()
            lines = [
                Line(r.id, r.txn_date, r.credit, r.debit, r.description, r.reference, r.bank_account_id)
                for r in rows_all if r.id not in claimed_r
            ]
            exps = []
            for e in self._repo.expected_between(d_from, d_to):
                if e.id in claimed_e:
                    continue
                accounts = {e.bank_account_id} if e.bank_account_id else {a.id for a in self._repo.accounts_for_mode(e.mode)}
                exps.append(Expected(e.id, e.amount, e.win_from, e.win_to, e.reference, e.direction, accounts))
            made = {"auto": 0, "suggested": 0, "reversals": reversal_count}
            for p in propose(exps, lines, fee):
                match = self._repo.add_match(BankMatch(
                    kind="match", status="confirmed" if p.auto else "suggested", rule=p.kind, auto=p.auto, charges=money(p.charges),
                    note=p.note, created_by_id=actor_user_id,
                    confirmed_by_id=actor_user_id if p.auto else None, confirmed_at=datetime.now(timezone.utc) if p.auto else None,
                ))
                for eid in p.expected_ids:
                    match.items.append(BankMatchItem(expected_id=eid))
                for rid in p.line_ids:
                    match.items.append(BankMatchItem(row_id=rid))
                self._repo.save_match(match)
                made["auto" if p.auto else "suggested"] += 1
                self._audit_repo.record(
                    event_type="bank_match_auto" if p.auto else "bank_match_suggested", actor_id=actor_user_id, entity_type="BankMatch",
                    entity_id=match.id, description=f"{p.kind}: {len(p.expected_ids)} expected with {len(p.line_ids)} bank line(s). {p.note}",
                )
            return made

    def _pair_reversals(self, actor_user_id: str, rows, claimed_r) -> int:
        lines = [Line(r.id, r.txn_date, r.credit, r.debit, r.description, r.reference, r.bank_account_id) for r in rows]
        done = 0
        for credit_id, debit_id in find_reversals(lines):
            if debit_id in claimed_r:
                continue
            live = self._live_matches_of_row(credit_id)
            if any(m.kind == "reversal" for m in live) or any(m.locked for m in live):
                continue  # already paired, or an owner locked the credit's match: left alone and shown as an exception
            for m in live:  # an earlier match of the credit is undone: that money did not stay
                if m.kind == "match":
                    self._void(m, actor_user_id, "The bank reversed this credit", event="bank_match_voided_by_reversal")
            match = self._repo.add_match(BankMatch(
                kind="reversal", status="confirmed", rule="reversal", auto=True, charges=_Z, note="A bank debit undoes this credit",
                created_by_id=actor_user_id, confirmed_by_id=actor_user_id, confirmed_at=datetime.now(timezone.utc),
            ))
            match.items.append(BankMatchItem(row_id=credit_id))
            match.items.append(BankMatchItem(row_id=debit_id))
            self._repo.save_match(match)
            done += 1
            self._audit_repo.record(
                event_type="bank_reversal_paired", actor_id=actor_user_id, entity_type="BankMatch", entity_id=match.id,
                description="A reversal on the statement was paired with the credit it undid",
            )
        return done

    def _live_matches_of_row(self, row_id: str) -> List[BankMatch]:
        return [m for m in self._repo.live_matches() if any(i.row_id == row_id for i in m.items)]

    def _void(self, match: BankMatch, actor_id: str, reason: str, event: str = "bank_match_unmatched") -> None:
        match.status, match.voided_by_id, match.voided_at, match.void_reason = "void", actor_id, datetime.now(timezone.utc), reason
        self._repo.save_match(match)
        self._audit_repo.record(
            event_type=event, actor_id=actor_id, entity_type="BankMatch", entity_id=match.id, description=f"Match undone: {reason}",
        )

    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def confirm(self, actor_user_id: str, match_id: str) -> BankMatch:
        with unit_of_work(self._session):
            m = self._get_match(match_id)
            if m.status != "suggested":
                raise ConflictError("Only a suggestion can be confirmed")
            m.status, m.confirmed_by_id, m.confirmed_at = "confirmed", actor_user_id, datetime.now(timezone.utc)
            self._repo.save_match(m)
            self._audit_repo.record(event_type="bank_match_confirmed", actor_id=actor_user_id, entity_type="BankMatch", entity_id=m.id,
                                    description=f"Confirmed a suggested match ({m.rule})")
            return m

    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def reject(self, actor_user_id: str, match_id: str, reason: str) -> BankMatch:
        if not (reason or "").strip():
            raise ValueError("A reason is required")
        with unit_of_work(self._session):
            m = self._get_match(match_id)
            if m.status != "suggested":
                raise ConflictError("Only a suggestion can be rejected")
            self._void(m, actor_user_id, reason.strip(), event="bank_suggestion_rejected")
            return m

    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def manual_match(self, actor_user_id: str, expected_ids: List[str], row_ids: List[str], reason: str) -> BankMatch:
        if not expected_ids or not row_ids:
            raise ValueError("Pick at least one expected payment and one bank line")
        if not (reason or "").strip():
            raise ValueError("A reason is required for a manual match")
        with unit_of_work(self._session):
            exps, rows = self._repo.expected_by_ids(expected_ids), self._repo.rows_by_ids(row_ids)
            if len(exps) != len(set(expected_ids)) or len(rows) != len(set(row_ids)):
                raise NotFoundError("One of the chosen items was not found")
            ce, cr = self._repo.claimed_ids()
            if any(e.id in ce for e in exps) or any(r.id in cr for r in rows):
                raise ConflictError("One of these is already in another match: undo that match first")
            direction = exps[0].direction
            if any(e.direction != direction for e in exps):
                raise ValueError("Money in and money out cannot be matched together")
            expected_total = sum((e.amount for e in exps), _Z)
            got = sum(((r.credit if direction == "credit" else r.debit) for r in rows), _Z)
            if got > expected_total:
                raise ValueError(f"The bank lines add up to {got}, more than the {expected_total} expected")
            m = self._repo.add_match(BankMatch(
                kind="match", status="confirmed", rule="manual", auto=False, charges=money(expected_total - got),
                note=reason.strip(), created_by_id=actor_user_id, confirmed_by_id=actor_user_id, confirmed_at=datetime.now(timezone.utc),
            ))
            for e in exps:
                m.items.append(BankMatchItem(expected_id=e.id))
            for r in rows:
                m.items.append(BankMatchItem(row_id=r.id))
            self._repo.save_match(m)
            self._audit_repo.record(
                event_type="bank_match_manual", actor_id=actor_user_id, entity_type="BankMatch", entity_id=m.id,
                description=f"Matched by hand: expected {expected_total}, received {got}, charges {m.charges}. {reason.strip()}",
            )
            return m

    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def unmatch(self, actor_user_id: str, match_id: str, reason: str) -> BankMatch:
        if not (reason or "").strip():
            raise ValueError("A reason is required to undo a match")
        with unit_of_work(self._session):
            m = self._get_match(match_id)
            if m.status == "void":
                raise ConflictError("This match is already undone")
            if m.locked:
                raise ConflictError("An owner locked this match: only an owner can unlock it first")
            self._void(m, actor_user_id, reason.strip())
            return m

    @require_permission(Permission.BANK_RECON_MANAGE.value)
    def mark_not_ours(self, actor_user_id: str, row_id: str, reason: str) -> BankMatch:
        if not (reason or "").strip():
            raise ValueError("Say why this bank line is not the pump's")
        with unit_of_work(self._session):
            row = self._repo.get_row(row_id)
            if row is None:
                raise NotFoundError("Bank line not found")
            if row_id in self._repo.claimed_ids()[1]:
                raise ConflictError("This bank line is already in a match: undo that first")
            m = self._repo.add_match(BankMatch(
                kind="not_ours", status="confirmed", rule="not_ours", auto=False, charges=_Z, note=reason.strip(),
                created_by_id=actor_user_id, confirmed_by_id=actor_user_id, confirmed_at=datetime.now(timezone.utc),
            ))
            m.items.append(BankMatchItem(row_id=row_id))
            self._repo.save_match(m)
            self._audit_repo.record(event_type="bank_row_not_ours", actor_id=actor_user_id, entity_type="BankStatementRow", entity_id=row_id,
                                    description=f"Marked not the pump's: {row.description[:80]} ({row.credit or row.debit}). {reason.strip()}")
            return m

    @require_permission(Permission.BANK_RECON_LOCK.value)
    def lock(self, actor_user_id: str, match_id: str, locked: bool = True) -> BankMatch:
        with unit_of_work(self._session):
            m = self._get_match(match_id)
            if m.status != "confirmed":
                raise ConflictError("Only a confirmed match can be locked")
            m.locked = locked
            m.locked_by_id, m.locked_at = (actor_user_id, datetime.now(timezone.utc)) if locked else (None, None)
            self._repo.save_match(m)
            self._audit_repo.record(event_type="bank_match_locked" if locked else "bank_match_unlocked", actor_id=actor_user_id,
                                    entity_type="BankMatch", entity_id=m.id, description="Owner locked the match" if locked else "Owner unlocked the match")
            return m

    def _get_match(self, match_id: str) -> BankMatch:
        m = self._repo.get_match(match_id)
        if m is None:
            raise NotFoundError("Match not found")
        return m

    # -- reading: the day view and the exceptions -------------------------------------------------------------------------------------
    def build_days(self, d_from: date, d_to: date, today: Optional[date] = None) -> List[DayMode]:
        """Internal (no permission check; the checks use it): per day and payment mode, expected against received."""
        today = today or date.today()
        exps = self._repo.expected_between(d_from, d_to)
        ce, _ = self._repo.claimed_ids(("confirmed",))
        cs, _ = self._repo.claimed_ids(("suggested",))
        matches = {m.id: m for m in self._repo.live_matches()}
        group_total: Dict[str, Decimal] = {}
        for mid, m in matches.items():
            group_total[mid] = sum((self._expected_amount(i) for i in m.items if i.expected_id), _Z)
        out: Dict[tuple, DayMode] = {}
        for e in exps:
            cell = out.setdefault((e.business_date, e.mode), DayMode(e.business_date, e.mode, MODE_LABELS.get(e.mode, e.mode)))
            cell.expected += e.amount
            if e.id in ce:
                m = matches[ce[e.id]]
                total = group_total[m.id] or e.amount
                share = (m.charges * e.amount / total) if total else _Z
                cell.charges += share
                cell.received += e.amount - share
            elif e.id in cs:
                cell.suggested += e.amount
            else:
                cell.unmatched += e.amount
                if e.win_to >= today:
                    cell.awaiting = True
        for cell in out.values():
            cell.expected, cell.received, cell.charges = money(cell.expected), money(cell.received), money(cell.charges)
            cell.suggested, cell.unmatched = money(cell.suggested), money(cell.unmatched)
            if cell.unmatched > 0:
                cell.status = "awaiting" if cell.awaiting else "unmatched"
            elif cell.suggested > 0:
                cell.status = "suggested"
            else:
                cell.status = "matched"
        return sorted(out.values(), key=lambda c: (c.day, ALL_MODES.index(c.mode) if c.mode in ALL_MODES else 99))

    def _expected_amount(self, item: BankMatchItem) -> Decimal:
        return item.expected.amount if item.expected is not None else _Z

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def day_view(self, actor_user_id: str, d_from: date, d_to: date) -> List[DayMode]:
        return self.build_days(d_from, d_to)

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def exceptions(self, actor_user_id: str, d_from: date, d_to: date) -> Exceptions:
        today = date.today()
        _, claimed_rows = self._repo.claimed_ids(("confirmed", "suggested"))
        out = Exceptions()
        out.unmatched_credits = [r for r in self._repo.rows_between(d_from, d_to) if r.credit > 0 and r.id not in claimed_rows]
        ce, cs = self._repo.claimed_ids(("confirmed",))[0], self._repo.claimed_ids(("suggested",))[0]
        for e in self._repo.expected_between(d_from, d_to):
            if e.id not in ce and e.id not in cs:
                out.aged_expected.append((e, max(0, (today - e.business_date).days)))
        out.aged_expected.sort(key=lambda t: -t[1])
        out.total_charges = money(sum((m.charges for m in self._repo.confirmed_matches() if m.kind == "match"), _Z))
        out.suggestions = len(self._repo.pending_suggestions())
        for acct in self._repo.list_accounts():
            out.broken_imports += [i for i in self._repo.imports_for_account(acct.id) if not i.continuity_ok]
        return out

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def suggestions(self, actor_user_id: str) -> List[BankMatch]:
        return self._repo.pending_suggestions()

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def rows(self, actor_user_id: str, d_from: date, d_to: date, account_id: Optional[str] = None) -> List[BankStatementRow]:
        return self._repo.rows_between(d_from, d_to, account_id)

    @require_permission(Permission.BANK_RECON_VIEW.value)
    def expected(self, actor_user_id: str, d_from: date, d_to: date) -> List[ExpectedReceipt]:
        return self._repo.expected_between(d_from, d_to)

    def match_state(self):
        """(expected id -> match, row id -> match) for live matches, for the screen."""
        ce, cr = self._repo.claimed_ids(("suggested", "confirmed"))
        matches = {m.id: m for m in self._repo.live_matches()}
        return {k: matches[v] for k, v in ce.items()}, {k: matches[v] for k, v in cr.items()}
