"""Shift close entry: type the closing master readings of a shift in one go (no attendants, no per-sale records)."""

from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, Out, VolumeIn, VolumeOut
from api.services import Services
from app.services.shift_close_service import Reading

router = APIRouter(tags=["shift-close"])


class CloseLineOut(Out):
    nozzle_id: str
    code: str
    fuel: str
    tank: Optional[str] = None
    opening: Optional[VolumeOut] = None
    closed: bool
    closing: Optional[VolumeOut] = None
    testing: VolumeOut


class ShiftCloseReadingIn(In):
    nozzle_id: str
    closing: VolumeIn
    testing: VolumeIn = "0"
    opening: Optional[VolumeIn] = None


class CloseEntryIn(In):
    readings: list[ShiftCloseReadingIn]


def _out(lines) -> list[CloseLineOut]:
    return [CloseLineOut.model_validate(l, from_attributes=True) for l in lines]


@router.get("/shift-close/{shift_id}", response_model=list[CloseLineOut])
def sheet(shift_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _out(services.shift_close.sheet(user.id, shift_id))


@router.post("/shift-close/{shift_id}", response_model=list[CloseLineOut])
def submit(shift_id: str, body: CloseEntryIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    readings = [Reading(r.nozzle_id, r.closing, r.testing, r.opening) for r in body.readings]
    return _out(services.shift_close.submit(user.id, shift_id, readings))
