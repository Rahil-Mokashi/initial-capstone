"""Shift cash custody (docs/daily-report-spec.md section 4; A1 in
PROJECT_CONTEXT.md's working assumptions, Step 3 of the settlement-side
build). Records the two custody transfers a shift's cash book shows on
its receipt side - Advance (an interim handover during the shift) and
Final (the handover at close) - as physical cash moving from the shift
till into the office's hands, not an expense or a sale.

The rest of the cash book (opening balance carried forward, bank
deposits, derived closing cash-in-hand) is Step 4, built on top of what
this records rather than duplicating it.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.shift_cash_book import ShiftCashBook
from app.schemas.shift_cash_book import ShiftCashBookRecord


class ShiftCashBookService:
    def __init__(self, cash_book_repo, shift_repo, audit_repo, auth_service):
        self._cash_book_repo = cash_book_repo
        self._shift_repo = shift_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

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
