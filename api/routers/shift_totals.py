"""The cashier's per-payment-mode totals for a shift, and internal fuel use (an expense with litres)."""

from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out, VolumeIn, VolumeOut
from api.services import Services
from app.services.tender_entry_service import report_label

router = APIRouter(tags=["shift-totals"])


class TenderTotalOut(Out):
    tender_id: str
    name: str
    label: str
    amount: Optional[MoneyOut] = None
    reference: Optional[str] = None


class TotalIn(In):
    amount: MoneyIn
    reference: Optional[str] = None
    reason: OptionalReason


class InternalFuelIn(In):
    shift_id: str
    employee_id: str
    fuel_id: str
    litres: VolumeIn
    vehicle: str


class InternalFuelOut(Out):
    id: str
    expense_id: str
    litres: VolumeOut
    rate: MoneyOut
    vehicle: str


def _rows(services: Services, user_id: str, shift_id: str) -> list[TenderTotalOut]:
    entered = {e.tender_id: e for e in services.tender_entries.list_for_shift(user_id, shift_id)}
    out = []
    for t in services.tender_entries.entry_tenders(user_id):
        e = entered.get(t.id)
        out.append(TenderTotalOut(
            tender_id=t.id, name=t.name, label=report_label(t.name),
            amount=e.amount if e else None, reference=e.reference if e else None,
        ))
    return out


@router.get("/shift-totals/{shift_id}", response_model=list[TenderTotalOut])
def shift_totals(shift_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _rows(services, user.id, shift_id)


@router.put("/shift-totals/{shift_id}/{tender_id}", response_model=list[TenderTotalOut])
def set_total(shift_id: str, tender_id: str, body: TotalIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.tender_entries.set_total(user.id, shift_id, tender_id, body.amount, body.reference, body.reason)
    return _rows(services, user.id, shift_id)


@router.post("/internal-fuel", response_model=InternalFuelOut, status_code=201)
def internal_fuel(body: InternalFuelIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return InternalFuelOut.model_validate(
        services.internal_fuel.record(user.id, body.shift_id, body.employee_id, body.fuel_id, body.litres, body.vehicle)
    )
