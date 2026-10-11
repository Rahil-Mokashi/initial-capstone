"""Dispensers and nozzles. Same NozzleService calls as app/ui/nozzle_window.py."""

from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services, require_permission
from api.schemas import In, OptionalReason, Out
from api.services import Services
from app.core.constants import NozzleStatus, Permission
from app.database.base import StatusEnum
from app.schemas.nozzle import DispenserCreate, NozzleCreate

router = APIRouter(tags=["nozzles"])


class DispenserOut(Out):
    id: str
    code: str
    status: str


class NozzleOut(Out):
    id: str
    code: str
    dispenser_id: str
    dispenser: Optional[str] = None
    fuel_id: str
    fuel_type: Optional[str] = None
    tank_id: Optional[str] = None
    status: str


class FuelOption(Out):
    id: str
    fuel_type: str


class TankOption(Out):
    id: str
    label: str


class NozzleOptions(Out):
    """What the Add Nozzle dialog offers: active dispensers, active fuels, active tanks."""

    dispensers: list[DispenserOut]
    fuels: list[FuelOption]
    tanks: list[TankOption]


class DispenserIn(In):
    code: str


class NozzleIn(In):
    code: str
    dispenser_id: str
    fuel_id: str
    tank_id: Optional[str] = None


class DispenserStatusIn(In):
    status: StatusEnum
    reason: OptionalReason


class NozzleStatusIn(In):
    status: NozzleStatus
    reason: OptionalReason


def nozzle_out(n) -> NozzleOut:
    return NozzleOut(
        id=n.id,
        code=n.code,
        dispenser_id=n.dispenser_id,
        dispenser=n.dispenser.code if n.dispenser else None,
        fuel_id=n.fuel_id,
        fuel_type=n.fuel.fuel_type if n.fuel else None,
        tank_id=getattr(n, "tank_id", None),
        status=n.status,
    )


@router.get("/dispensers", response_model=list[DispenserOut])
def list_dispensers(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.nozzles.list_dispensers(user.id)


@router.post("/dispensers", response_model=DispenserOut, status_code=201)
def create_dispenser(body: DispenserIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.nozzles.create_dispenser(user.id, DispenserCreate(code=body.code))


@router.post("/dispensers/{dispenser_id}/status", response_model=DispenserOut)
def set_dispenser_status(
    dispenser_id: str, body: DispenserStatusIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return services.nozzles.set_dispenser_status(user.id, dispenser_id, body.status, body.reason)


@router.get("/nozzles", response_model=list[NozzleOut])
def list_nozzles(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [nozzle_out(n) for n in services.nozzles.list_nozzles(user.id)]


@router.get("/nozzles/options", response_model=NozzleOptions)
def nozzle_options(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """The Qt Add Nozzle dialog reads dispensers, FuelRepository and TankRepository; it is only shown to NOZZLE_MANAGE."""
    require_permission(services, user.id, Permission.NOZZLE_MANAGE)
    return NozzleOptions(
        dispensers=[d for d in services.nozzles.list_dispensers(user.id) if d.status == "active"],
        fuels=[FuelOption(id=f.id, fuel_type=f.fuel_type) for f in services.fuel_repo.list_active()],
        tanks=[
            TankOption(id=t.id, label=f"{t.code} ({t.fuel.fuel_type if t.fuel else ''})")
            for t in services.tank_repo.list_all()
            if t.status == "active"
        ],
    )


@router.post("/nozzles", response_model=NozzleOut, status_code=201)
def create_nozzle(body: NozzleIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return nozzle_out(services.nozzles.create_nozzle(user.id, NozzleCreate(**body.model_dump())))


@router.post("/nozzles/{nozzle_id}/status", response_model=NozzleOut)
def set_nozzle_status(
    nozzle_id: str, body: NozzleStatusIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return nozzle_out(services.nozzles.set_nozzle_status(user.id, nozzle_id, body.status, body.reason))
