"""The one place that enforces the review chain, whichever screen or service writes (LAN build, Phase 4).

A Session `before_flush` listener looks at every row about to be added, changed or deleted. If it belongs to a shift (Sale, Payment,
nozzle assignment, tender total, cash book, expense, oil sale, bowser bill, reconciliation) then:
  * shift is LOCKED   -> the save is refused (ConflictError), nothing is written;
  * shift is VERIFIED or APPROVED -> the shift goes back to ENTERED and the move is recorded ("data changed").
A reopen by an owner is the only way back from LOCKED. Installed once, in api.app.create_app.
"""

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models.shift_entry import APPROVED, ENTERED, LOCKED, VERIFIED, ShiftEntry, ShiftEntryEvent

_INSTALLED = False


def _guarded_models() -> tuple:
    from app.models.bowser import BowserBill, BowserTransfer
    from app.models.expense import Expense
    from app.models.lubricant import LubricantMovement
    from app.models.nozzle_assignment import NozzleAssignment
    from app.models.payment import Payment
    from app.models.sale import Sale
    from app.models.shift_cash_book import ShiftCashBook
    from app.models.shift_reconciliation import ShiftReconciliation
    from app.models.shift_tender_entry import ShiftTenderEntry

    return (Sale, Payment, NozzleAssignment, ShiftCashBook, ShiftTenderEntry, Expense, LubricantMovement, BowserTransfer, BowserBill, ShiftReconciliation)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    models = _guarded_models()

    @event.listens_for(Session, "before_flush")
    def guard(session: Session, flush_context, instances) -> None:
        touched: set[str] = set()
        for obj in list(session.new) + list(session.deleted):
            if isinstance(obj, models) and getattr(obj, "shift_id", None):
                touched.add(obj.shift_id)
        for obj in session.dirty:
            if isinstance(obj, models) and getattr(obj, "shift_id", None) and session.is_modified(obj):
                touched.add(obj.shift_id)
        if not touched:
            return
        with session.no_autoflush:
            for shift_id in touched:
                entry = session.query(ShiftEntry).filter_by(shift_id=shift_id).first()
                if entry is None:
                    continue
                if entry.status == LOCKED:
                    raise ConflictError("This shift is locked. An owner has to reopen it (with a reason) before anything can change.")
                if entry.status in (VERIFIED, APPROVED):
                    before = entry.status
                    entry.status = ENTERED
                    session.add(
                        ShiftEntryEvent(
                            shift_entry_id=entry.id, from_status=before, to_status=ENTERED, action="data_changed",
                            reason="Figures were changed after this was checked",
                        )
                    )
