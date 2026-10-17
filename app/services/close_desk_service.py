"""The Close Shift desk: one place to type a shift's closing readings and how the money was collected, with the tally beside it.

It adds NO new accounting. It calls the services that already own each part (ShiftCloseService for the meters, TenderEntryService
for Card/DTP/Phone Pay/PTM/Other, ShiftCashBookService for Advance and Final) inside ONE unit of work, then reads the owner's own
formula back from the daily report (docs/daily-report-spec.md):

    Shift Total = CreditSale + CARD + DTP Card + Other + PHONE PAY + PTM + Expenses + Advance + Final   must equal   Total Sale

The difference (Total Sale minus that sum) is the shortage (positive) or excess (negative).

A preview runs the very same writes and then rolls them ALL back, so the figures shown while typing can never differ from the
figures that will be saved: there is only one formula and it is the report's.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.constants import Permission, ShiftStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import money
from app.core.permissions import require_permission
from app.repositories.base import session_for, unit_of_work
from app.schemas.shift_cash_book import ShiftCashBookRecord
from app.services.shift_close_service import NozzleLine, Reading
from app.services.tender_entry_service import DTP_TENDER, report_label

TOLERANCE = Decimal("0.01")  # one paisa: the same tolerance the report's own check uses
_Z = Decimal("0")


@dataclass
class ModeRow:
    tender_id: str
    name: str
    label: str
    amount: Optional[Decimal]
    read_only: bool = False  # DTP Card: the sum of the shift's Terminal DTP sales, never typed
    count: Optional[int] = None


@dataclass
class CashRow:
    advance: Decimal
    final: Decimal
    recorded: bool  # Advance and Final are written once per shift; after that they are shown, not typed


@dataclass
class Tally:
    fuel_rs: Decimal
    oil_rs: Decimal
    total_sale: Decimal
    lines: List[tuple]  # (label, amount) in the report's order
    collected: Decimal
    difference: Decimal  # total sale - collected: positive = SHORT, negative = EXCESS
    status: str  # balanced | short | excess
    credit_count: int = 0
    expenses_count: int = 0
    pending_expenses: int = 0


@dataclass
class Desk:
    shift_id: str
    nozzles: List[NozzleLine]
    modes: List[ModeRow]
    cash: CashRow
    tally: Tally
    default_testing: Decimal = _Z
    notes: List[str] = field(default_factory=list)


def tally_status(block) -> tuple:
    """(difference, status) of one shift block of the daily report: Total Sale minus everything collected. The one formula, used by
    the Close Shift desk and by the daily digest."""
    difference = money(block.total_sale - block.lines_total)
    status = "balanced" if abs(difference) <= TOLERANCE else ("short" if difference > 0 else "excess")
    return difference, status


class _PreviewDone(Exception):
    def __init__(self, desk: Desk):
        self.desk = desk


class CloseDeskService:
    def __init__(self, shift_close, tender_entries, cash_book, daily_report, shift_repo, settings, auth_service, workflow=None, shift_service=None):
        self._close = shift_close
        self._tenders = tender_entries
        self._cash = cash_book
        self._report = daily_report
        self._shifts = shift_repo
        self._settings = settings
        self._auth_service = auth_service
        self._workflow = workflow
        self._shift_service = shift_service
        self._session = session_for(shift_repo)

    @require_permission(Permission.SHIFT_VIEW.value)
    def desk(self, actor_user_id: str, shift_id: str) -> Desk:
        return self._build(actor_user_id, shift_id)

    @require_permission(Permission.SHIFT_MANAGE.value)
    def close(
        self,
        actor_user_id: str,
        shift_id: str,
        readings: List[Reading],
        modes: Dict[str, Decimal],
        advance: Optional[Decimal] = None,
        final: Optional[Decimal] = None,
        preview: bool = False,
    ) -> Desk:
        """Save everything typed, all or nothing. With preview=True nothing is kept: the same writes run and are rolled back."""
        if self._shifts.get_by_id(shift_id) is None:
            raise NotFoundError(f"Shift not found: {shift_id}")
        try:
            with unit_of_work(self._session):
                if readings:
                    self._close.submit(actor_user_id, shift_id, readings)
                dtp_ids = {t.id for t in self._tenders.entry_tenders(actor_user_id) if t.name == DTP_TENDER}
                for tender_id, amount in modes.items():
                    if tender_id in dtp_ids:
                        raise ConflictError("DTP Card is worked out from the DTP sales entered on the Terminal; it is not typed here.")
                    self._tenders.set_total(actor_user_id, shift_id, tender_id, amount)
                self._record_cash(actor_user_id, shift_id, advance, final)
                self._session.flush()
                if self._workflow is not None:
                    self._workflow.mark_entered(actor_user_id, shift_id)  # the figures were typed: the review chain starts
                if not preview and self._shift_service is not None:
                    # Pressing Close shift closes the shift (an already closed one being corrected stays as it is).
                    if self._shifts.get_by_id(shift_id).status == ShiftStatus.OPEN.value:
                        self._shift_service.close_shift(actor_user_id, shift_id)
                desk = self._build(actor_user_id, shift_id)
                if preview:
                    raise _PreviewDone(desk)
                return desk
        except _PreviewDone as done:
            return done.desk

    def _record_cash(self, actor_user_id: str, shift_id: str, advance: Optional[Decimal], final: Optional[Decimal]) -> None:
        if advance is None and final is None:
            return
        existing = self._cash.get_for_shift(actor_user_id, shift_id)
        if existing is None:
            self._cash.record_shift_cash_movements(
                actor_user_id, ShiftCashBookRecord(shift_id=shift_id, advance_amount=money(advance or _Z), final_amount=money(final or _Z))
            )
            return
        same_advance = advance is None or money(advance) == existing.advance_amount
        same_final = final is None or money(final) == existing.final_amount
        if not (same_advance and same_final):
            raise ConflictError("Advance and Final were already recorded for this shift and cannot be changed here.")

    def _build(self, actor_user_id: str, shift_id: str) -> Desk:
        shift = self._shifts.get_by_id(shift_id)
        if shift is None:
            raise NotFoundError(f"Shift not found: {shift_id}")
        nozzles = self._close.sheet(actor_user_id, shift_id)
        typed = {e.tender_id: e.amount for e in self._tenders.list_for_shift(actor_user_id, shift_id)}
        dtp_total, dtp_count = self._tenders.dtp_from_sales(shift_id)
        modes = [
            ModeRow(t.id, t.name, report_label(t.name), dtp_total, True, dtp_count)
            if t.name == DTP_TENDER
            else ModeRow(t.id, t.name, report_label(t.name), typed.get(t.id))
            for t in self._tenders.entry_tenders(actor_user_id)
        ]
        book = self._cash.get_for_shift(actor_user_id, shift_id)
        cash = CashRow(
            advance=book.advance_amount if book else _Z, final=book.final_amount if book else _Z, recorded=book is not None
        )
        return Desk(
            shift_id=shift_id, nozzles=nozzles, modes=modes, cash=cash, tally=self._tally(actor_user_id, shift.shift_date, shift_id),
            default_testing=self._settings.get_decimal("default_testing_litres"),
        )

    def _tally(self, actor_user_id: str, day: date, shift_id: str) -> Tally:
        report = self._report.compute(day, actor_user_id)
        block = next((b for b in report.shifts if b.shift_id == shift_id), None)
        if block is None:
            return Tally(_Z, _Z, _Z, [], _Z, _Z, "balanced")
        difference, status = tally_status(block)
        return Tally(
            fuel_rs=block.fuel_rs, oil_rs=block.oil_rs, total_sale=block.total_sale, lines=list(block.lines),
            collected=block.lines_total, difference=difference, status=status, credit_count=len(block.credit_sales),
            expenses_count=len(block.expenses), pending_expenses=block.pending_expenses,
        )
