"""The Close Shift desk: closing readings + money collected + the tally, in one screen's worth of calls.

Thin: CloseDeskService does the work. `/tally` runs the same writes as `/` and rolls them back, so it never saves anything.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.routers.shift_close import CloseLineOut, ShiftCloseReadingIn
from api.schemas import In, MoneyIn, MoneyOut, Out, VolumeOut
from api.services import Services
from app.services.shift_close_service import Reading

router = APIRouter(tags=["close-desk"])


class DeskModeOut(Out):
    tender_id: str
    name: str
    label: str
    amount: Optional[MoneyOut] = None


class DeskCashOut(Out):
    advance: MoneyOut
    final: MoneyOut
    recorded: bool


class DeskLineOut(Out):
    label: str
    amount: MoneyOut


class DeskTallyOut(Out):
    fuel_rs: MoneyOut
    oil_rs: MoneyOut
    total_sale: MoneyOut
    lines: list[DeskLineOut]
    collected: MoneyOut
    difference: MoneyOut
    status: str
    credit_count: int
    expenses_count: int
    pending_expenses: int


class DeskOut(Out):
    shift_id: str
    nozzles: list[CloseLineOut]
    modes: list[DeskModeOut]
    cash: DeskCashOut
    tally: DeskTallyOut
    default_testing: VolumeOut


class DeskModeIn(In):
    tender_id: str
    amount: MoneyIn


class DeskIn(In):
    readings: list[ShiftCloseReadingIn] = []
    modes: list[DeskModeIn] = []
    advance: Optional[MoneyIn] = None
    final: Optional[MoneyIn] = None


def _out(desk) -> DeskOut:
    tally = desk.tally
    return DeskOut(
        shift_id=desk.shift_id,
        nozzles=[CloseLineOut.model_validate(n, from_attributes=True) for n in desk.nozzles],
        modes=[DeskModeOut.model_validate(m, from_attributes=True) for m in desk.modes],
        cash=DeskCashOut.model_validate(desk.cash, from_attributes=True),
        tally=DeskTallyOut(
            fuel_rs=tally.fuel_rs, oil_rs=tally.oil_rs, total_sale=tally.total_sale,
            lines=[DeskLineOut(label=label, amount=amount) for label, amount in tally.lines],
            collected=tally.collected, difference=tally.difference, status=tally.status, credit_count=tally.credit_count,
            expenses_count=tally.expenses_count, pending_expenses=tally.pending_expenses,
        ),
        default_testing=desk.default_testing,
    )


def _run(shift_id: str, body: DeskIn, user: CurrentUser, services: Services, preview: bool) -> DeskOut:
    readings = [Reading(r.nozzle_id, r.closing, r.testing, r.opening) for r in body.readings]
    modes = {m.tender_id: m.amount for m in body.modes}
    return _out(services.close_desk.close(user.id, shift_id, readings, modes, body.advance, body.final, preview))


@router.get("/close-shift/{shift_id}", response_model=DeskOut)
def desk(shift_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _out(services.close_desk.desk(user.id, shift_id))


@router.post("/close-shift/{shift_id}/tally", response_model=DeskOut)
def tally(shift_id: str, body: DeskIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """What the tally WOULD be with these figures. Nothing is saved."""
    return _run(shift_id, body, user, services, preview=True)


@router.post("/close-shift/{shift_id}", response_model=DeskOut)
def close(shift_id: str, body: DeskIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _run(shift_id, body, user, services, preview=False)
