"""The cashier's per-payment-mode totals for a shift (Card, DTP Card, Phone Pay, PTM, Other).

Reuses the existing reconciliation permissions: typing a shift's tender totals is part of the
same job as declaring them. Append-only: a re-typed total voids the old entry (kept, with a reason).
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission, TenderSettlementType
from app.core.exceptions import NotFoundError
from app.core.money import money
from app.core.permissions import require_permission
from app.models.shift_tender_entry import ShiftTenderEntry
from app.repositories.base import session_for, unit_of_work

# What the paper report calls each mode. A tender not listed prints under its own name, so a newly
# seeded tender needs no code change.
REPORT_LABELS = {"Card": "CARD", "DTP Card": "DTP Card", "PhonePe": "PHONE PAY", "Paytm": "PTM", "Other": "Other"}
# The order the report prints them in.
REPORT_ORDER = ["Card", "DTP Card", "Other", "PhonePe", "Paytm"]


def report_label(tender_name: str) -> str:
    return REPORT_LABELS.get(tender_name, tender_name)


class TenderEntryService:
    def __init__(self, entry_repo, tender_repo, shift_repo, audit_repo, auth_service):
        self._entries = entry_repo
        self._tenders = tender_repo
        self._shifts = shift_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(entry_repo)

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def entry_tenders(self, actor_user_id: str):
        """The payment modes a cashier types a total for: every bank-settled tender."""
        return self.typed_tenders()

    def typed_tenders(self):
        found = [t for t in self._tenders.list_active() if t.settlement_type == TenderSettlementType.BANK_SETTLED.value]
        rank = {n: i for i, n in enumerate(REPORT_ORDER)}
        return sorted(found, key=lambda t: (rank.get(t.name, 99), t.name))

    @require_permission(Permission.RECONCILIATION_MANAGE.value)
    def set_total(
        self, actor_user_id: str, shift_id: str, tender_id: str, amount: Decimal, reference: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> ShiftTenderEntry:
        if amount < 0:
            raise ValueError("A total cannot be negative")
        with unit_of_work(self._session):
            shift = self._shifts.get_by_id(shift_id)
            if shift is None:
                raise NotFoundError(f"Shift not found: {shift_id}")
            tender = self._tenders.get_by_id(tender_id)
            if tender is None:
                raise NotFoundError(f"Payment mode not found: {tender_id}")
            if tender.settlement_type != TenderSettlementType.BANK_SETTLED.value:
                raise ValueError(f"{tender.name} is not typed per shift: cash comes from the cash book and credit from the bills")
            amount = money(amount)
            old = self._entries.active_for_shift_tender(shift_id, tender_id)
            if old is not None:
                if old.amount == amount and (old.reference or None) == ((reference or "").strip() or None):
                    return old
                old.voided_at = datetime.now(timezone.utc)
                old.void_reason = (reason or "").strip() or "Replaced by a new total"
                self._entries.save(old)
            row = self._entries.add(ShiftTenderEntry(
                shift_id=shift_id, tender_id=tender_id, amount=amount,
                reference=(reference or "").strip() or None, recorded_by_id=actor_user_id,
            ))
            self._audit_repo.record(
                event_type="shift_tender_total_set", actor_id=actor_user_id, entity_type="ShiftTenderEntry",
                entity_id=row.id,
                description=f"{shift.shift_date} {shift.shift_label}: {tender.name} total {amount}"
                + (f" (was {old.amount})" if old is not None else ""),
                old_value=str(old.amount) if old is not None else None, new_value=str(amount),
            )
            return row

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def list_for_shift(self, actor_user_id: str, shift_id: str) -> List[ShiftTenderEntry]:
        return self._entries.active_for_shift(shift_id)

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def history_for_shift(self, actor_user_id: str, shift_id: str) -> List[ShiftTenderEntry]:
        return self._entries.history_for_shift(shift_id)

    # internal read for the report builder, checks and bank expectations (no permission check on purpose)
    def totals_for_shift(self, shift_id: str) -> dict:
        """tender name -> active typed total."""
        out = {}
        for e in self._entries.active_for_shift(shift_id):
            out[e.tender.name] = out.get(e.tender.name, Decimal("0")) + e.amount
        return out
