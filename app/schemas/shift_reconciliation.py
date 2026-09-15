from decimal import Decimal
from typing import Dict, Optional

from pydantic import BaseModel, field_validator


class ShiftReconciliationPerform(BaseModel):
    shift_id: str
    # tender_id -> declared amount. One entry per non-credit tender the
    # caller is declaring for - ReconciliationService computes which
    # tenders actually had expected activity that shift and requires a
    # declaration for each of those; an amount supplied for a tender
    # with no expected activity is simply ignored rather than erroring,
    # but a missing declaration for a tender that DID have activity is
    # rejected rather than silently treated as zero (see
    # ReconciliationService._perform_shift_reconciliation_impl).
    declared_amounts: Dict[str, Decimal]
    remarks: Optional[str] = None

    @field_validator("declared_amounts")
    @classmethod
    def non_negative(cls, value: Dict[str, Decimal]) -> Dict[str, Decimal]:
        for amount in value.values():
            if amount < 0:
                raise ValueError("declared amounts cannot be negative")
        return value
