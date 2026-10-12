"""Lubricant items and stock movements (the report's Oil sale table)."""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out, VolumeIn, VolumeOut
from api.services import Services

router = APIRouter(tags=["lubricants"])


class LubricantOut(Out):
    id: str
    name: str
    pack_size: Optional[str] = None
    default_rate: MoneyOut
    stock: VolumeOut


class LubricantIn(In):
    name: str
    pack_size: Optional[str] = None
    default_rate: MoneyIn


class LubricantRateIn(In):
    new_rate: MoneyIn
    reason: OptionalReason


class MovementIn(In):
    kind: Literal["opening", "purchase", "sale", "adjustment"]
    quantity: VolumeIn
    movement_date: Optional[date] = None
    unit_rate: Optional[MoneyIn] = None
    shift_id: Optional[str] = None
    customer_name: Optional[str] = None
    remarks: Optional[str] = None


class MovementOut(Out):
    id: str
    movement_date: date
    kind: str
    quantity: VolumeOut
    unit_rate: Optional[MoneyOut] = None
    amount: Optional[MoneyOut] = None
    shift_id: Optional[str] = None
    customer_name: Optional[str] = None
    remarks: Optional[str] = None


def _item(stock) -> LubricantOut:
    i = stock.item
    return LubricantOut(id=i.id, name=i.name, pack_size=i.pack_size, default_rate=i.default_rate, stock=stock.balance)


@router.get("/lubricants", response_model=list[LubricantOut])
def list_lubricants(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [_item(s) for s in services.lubricants.list_items(user.id)]


@router.post("/lubricants", response_model=LubricantOut, status_code=201)
def create_lubricant(body: LubricantIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    item = services.lubricants.create_item(user.id, body.name, body.pack_size, body.default_rate)
    return LubricantOut(id=item.id, name=item.name, pack_size=item.pack_size, default_rate=item.default_rate, stock=0)


@router.post("/lubricants/{item_id}/rate", response_model=LubricantOut)
def set_rate(item_id: str, body: LubricantRateIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.lubricants.set_default_rate(user.id, item_id, body.new_rate, body.reason)
    return next(_item(s) for s in services.lubricants.list_items(user.id) if s.item.id == item_id)


@router.get("/lubricants/{item_id}/movements", response_model=list[MovementOut])
def movements(item_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [MovementOut.model_validate(m) for m in services.lubricants.movements_for_item(user.id, item_id)]


@router.post("/lubricants/{item_id}/movements", response_model=MovementOut, status_code=201)
def record(item_id: str, body: MovementIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    m = services.lubricants.record_movement(
        user.id, item_id, body.kind, body.quantity, body.movement_date, body.unit_rate, body.shift_id,
        body.customer_name, body.remarks,
    )
    return MovementOut.model_validate(m)
