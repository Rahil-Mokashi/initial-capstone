"""Shift cash custody (docs/daily-report-spec.md section 4; A1 in
PROJECT_CONTEXT.md's working assumptions, Steps 3-4 of the settlement-
side build). Step 3 records the two custody transfers a shift's cash
book shows on its receipt side - Advance (an interim handover during
the shift) and Final (the handover at close) - as physical cash moving
from the shift till into the office's hands, not an expense or a sale.

Step 4 (this file's newer half) derives the rest of the cash book on
top of that: opening balance carried forward from the previous shift,
named bank deposits, and closing cash-in-hand - none of it stored,
all of it recomputed from Steps 3's own data plus ShiftBankDeposit,
the same "recompute rather than let it drift" discipline this project
already applies to CreditAccount's outstanding balance.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.shift_bank_deposit import ShiftBankDeposit
from app.models.shift_cash_book import ShiftCashBook
from app.schemas.shift_cash_book import ShiftBankDepositRecord, ShiftCashBookRecord


@dataclass
class ShiftCashBookSummary:
    """Everything the cash-book screen needs for one shift, in one
    call - opening_balance and closing_cash_in_hand are derived, never
    columns on any model (see ShiftCashBookService.get_opening_balance/
    get_closing_cash_in_hand)."""

    shift_id: str
    cash_book: Optional[ShiftCashBook]
    opening_balance: Decimal
    bank_deposits: List[ShiftBankDeposit] = field(default_factory=list)
    bank_deposits_total: Decimal = Decimal("0")
    # Employee cash-shortage recoveries posted into this shift's cash
    # book (Step 5, EmployeeShortageService.record_recovery) - a real
    # cash receipt, added on the same side as advance/final, not
    # subtracted like a bank deposit.
    shortage_recoveries: list = field(default_factory=list)
    shortage_recoveries_total: Decimal = Decimal("0")
    closing_cash_in_hand: Decimal = Decimal("0")


class ShiftCashBookService:
    def __init__(
        self, cash_book_repo, shift_repo, audit_repo, auth_service, bank_deposit_repo=None,
        shortage_recovery_repo=None,
    ):
        self._cash_book_repo = cash_book_repo
        self._shift_repo = shift_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        # Optional (Step 3's constructor shape, kept working unchanged):
        # only the Step 4 methods below (record_bank_deposit,
        # get_opening_balance, get_cash_book_summary) actually need it,
        # and each raises clearly rather than silently mis-deriving a
        # financial figure if it's missing.
        self._bank_deposit_repo = bank_deposit_repo
        # Optional the same way: only wired where a caller actually
        # exercises Step 5 (employee cash-shortage recovery). Missing
        # here means "recoveries aren't part of this computation" for a
        # caller that genuinely doesn't touch that feature, not a
        # silent zero for one that does - production wiring
        # (AppController in app/ui/main_window.py) always passes it.
        self._shortage_recovery_repo = shortage_recovery_repo

    # Reuses RECONCILIATION_MANAGE/RECONCILIATION_VIEW rather than a new
    # permission pair: this is the same actor, at the same workflow
    # moment (closing out a shift's cash position), as ShiftReconciliation
    # already gates on those two - the data is different, but who is
    # trusted to touch it is not.
    @require_permission(Permission.RECONCILIATION_MANAGE.value)
    def record_shift_cash_movements(self, actor_user_id: str, data: ShiftCashBookRecord) -> ShiftCashBook:
        shift = self._shift_repo.get_by_id(data.shift_id)
        if not shift:
            raise NotFoundError(f"Shift not found: {data.shift_id}")
        if self._cash_book_repo.get_by_shift_id(data.shift_id):
            raise ConflictError("This shift's cash movements have already been recorded")

        cash_book = ShiftCashBook(
            shift_id=data.shift_id,
            advance_amount=data.advance_amount,
            final_amount=data.final_amount,
            recorded_by_id=actor_user_id,
            recorded_at=datetime.now(timezone.utc),
        )
        cash_book = self._cash_book_repo.add(cash_book)

        self._audit_repo.record(
            event_type="shift_cash_movements_recorded",
            actor_id=actor_user_id,
            entity_type="ShiftCashBook",
            entity_id=cash_book.id,
            description=(
                f"Shift {shift.shift_date} {shift.shift_label}: advance {data.advance_amount:.2f}, "
                f"final {data.final_amount:.2f}"
            ),
        )
        return cash_book

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def get_for_shift(self, actor_user_id: str, shift_id: str) -> Optional[ShiftCashBook]:
        return self._cash_book_repo.get_by_shift_id(shift_id)

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def list_all(self, actor_user_id: str) -> List[ShiftCashBook]:
        return self._cash_book_repo.list_all()

    # ------------------------------------------------------------------
    # Step 4: bank deposits and the derived ledger
    # ------------------------------------------------------------------

    def _require_bank_deposit_repo(self) -> None:
        if self._bank_deposit_repo is None:
            raise ConflictError(
                "ShiftCashBookService needs a bank_deposit_repo to derive the cash book - see its constructor"
            )

    @require_permission(Permission.RECONCILIATION_MANAGE.value)
    def record_bank_deposit(self, actor_user_id: str, data: ShiftBankDepositRecord) -> ShiftBankDeposit:
        self._require_bank_deposit_repo()
        cash_book = self._cash_book_repo.get_by_shift_id(data.shift_id)
        if not cash_book:
            raise NotFoundError(
                f"No cash book recorded for shift {data.shift_id} yet - record advance/final first"
            )

        deposit = ShiftBankDeposit(
            shift_cash_book_id=cash_book.id,
            bank_name=data.bank_name,
            amount=data.amount,
            recorded_by_id=actor_user_id,
            recorded_at=datetime.now(timezone.utc),
        )
        deposit = self._bank_deposit_repo.add(deposit)

        self._audit_repo.record(
            event_type="shift_bank_deposit_recorded",
            actor_id=actor_user_id,
            entity_type="ShiftBankDeposit",
            entity_id=deposit.id,
            description=f"Deposited {data.amount:.2f} into {data.bank_name}",
        )
        return deposit

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def get_opening_balance(self, actor_user_id: str, shift_id: str) -> Decimal:
        shift = self._shift_repo.get_by_id(shift_id)
        if not shift:
            raise NotFoundError(f"Shift not found: {shift_id}")
        return self._opening_balance(shift)

    def _opening_balance(self, shift) -> Decimal:
        self._require_bank_deposit_repo()

        # Walk backward, one shift at a time, collecting the unbroken
        # run of cash books immediately preceding this shift - a shift
        # with no cash book recorded stops the chain there (its own
        # custody position is unknown, not assumed to be zero further
        # back than that gap). Iterative, not recursive: a mature site
        # can accumulate thousands of shifts, well past a safe Python
        # recursion depth.
        chain = []
        current = self._shift_repo.get_immediately_before(shift)
        while current is not None:
            cash_book = self._cash_book_repo.get_by_shift_id(current.id)
            if cash_book is None:
                break
            chain.append(cash_book)
            current = self._shift_repo.get_immediately_before(current)
        chain.reverse()  # oldest first, so the running balance telescopes forward correctly

        balance = Decimal("0")
        for cash_book in chain:
            deposits_total = sum(
                (d.amount for d in self._bank_deposit_repo.list_for_cash_book(cash_book.id)), Decimal("0")
            )
            recoveries_total = self._recoveries_total(cash_book)
            balance = (
                balance + cash_book.advance_amount + cash_book.final_amount
                + recoveries_total - deposits_total
            )
        return balance

    def _recoveries_total(self, cash_book: ShiftCashBook) -> Decimal:
        if self._shortage_recovery_repo is None:
            return Decimal("0")
        return sum(
            (r.amount for r in self._shortage_recovery_repo.list_for_cash_book(cash_book.id)), Decimal("0")
        )

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def get_cash_book_summary(self, actor_user_id: str, shift_id: str) -> ShiftCashBookSummary:
        self._require_bank_deposit_repo()
        shift = self._shift_repo.get_by_id(shift_id)
        if not shift:
            raise NotFoundError(f"Shift not found: {shift_id}")

        cash_book = self._cash_book_repo.get_by_shift_id(shift_id)
        opening_balance = self._opening_balance(shift)

        if cash_book is None:
            return ShiftCashBookSummary(
                shift_id=shift_id, cash_book=None, opening_balance=opening_balance,
            )

        deposits = self._bank_deposit_repo.list_for_cash_book(cash_book.id)
        deposits_total = sum((d.amount for d in deposits), Decimal("0"))
        recoveries = (
            self._shortage_recovery_repo.list_for_cash_book(cash_book.id)
            if self._shortage_recovery_repo is not None else []
        )
        recoveries_total = sum((r.amount for r in recoveries), Decimal("0"))
        closing_cash_in_hand = (
            opening_balance + cash_book.advance_amount + cash_book.final_amount
            + recoveries_total - deposits_total
        )
        return ShiftCashBookSummary(
            shift_id=shift_id,
            cash_book=cash_book,
            opening_balance=opening_balance,
            bank_deposits=deposits,
            bank_deposits_total=deposits_total,
            shortage_recoveries=recoveries,
            shortage_recoveries_total=recoveries_total,
            closing_cash_in_hand=closing_cash_in_hand,
        )
