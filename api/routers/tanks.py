"""Tanks & Inventory - the proof screen.

Each route calls the same TankService method the Qt window
(app/ui/tank_window.py) calls, with the signed-in user's id. Permission
checks live in the service (@require_permission); nothing is re-decided here.
The two lookups the Qt dialogs also use are gated through AuthService with
the permission the Qt screen implies (see each docstring).
"""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import CurrentUser, current_user, get_services
from api.schemas import (
    EmployeeOut,
    FuelOut,
    In,
    Out,
    ReadingIn,
    ReadingOut,
    ReconcileIn,
    ReconciliationOut,
    TankCreateIn,
    TankOut,
    TankStatusIn,
    TransactionIn,
    TransactionOut,
)
from api.services import Services
from app.core.constants import DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT, Permission
from app.core.exceptions import PermissionDeniedError
from app.schemas.tank import ReconciliationPerform, TankCreate, TankReadingCreate, TankTransactionCreate

router = APIRouter(tags=["tanks"])

_LOW = Decimal(str(DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT))


# --- presenters: shape ORM rows for the wire (no business rules) -------------
def tank_out(tank, services=None, user_id=None) -> TankOut:
    # Same clamp-to-0..100 display derivation as stock_percent() in app/ui/widgets.py.
    percent = Decimal(0) if tank.capacity <= 0 else max(Decimal(0), min(Decimal(100), tank.current_stock / tank.capacity * 100))
    height = basis = last_at = last_litres = None
    has_chart = False
    if services is not None:
        h, basis, has_chart = services.tank_dip_charts.drawing(tank)
        height = f"{h:.4f}"
        readings = services.tanks.list_readings(user_id, tank.id)
        if readings:
            last = max(readings, key=lambda r: r.reading_at)
            last_at, last_litres = last.reading_at, last.physical_stock
    return TankOut(
        id=tank.id,
        code=tank.code,
        fuel_id=tank.fuel_id,
        fuel_type=tank.fuel.fuel_type if tank.fuel else "",
        status=tank.status,
        capacity=tank.capacity,
        current_stock=tank.current_stock,
        opening_stock=tank.opening_stock,
        calibration_info=tank.calibration_info,
        fill_percent=percent,
        is_low=percent <= _LOW,
        fill_height=height,
        fill_basis=basis,
        has_dip_chart=has_chart,
        last_dip_at=last_at,
        last_dip_litres=last_litres,
    )


def transaction_out(txn) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        tank_id=txn.tank_id,
        tank_code=txn.tank.code if txn.tank else "",
        transaction_type=txn.transaction_type,
        quantity=txn.quantity,
        transaction_at=txn.transaction_at,
        reference=txn.reference,
        remarks=txn.remarks,
        recorded_by=txn.recorded_by.username if txn.recorded_by else "",
    )


def reading_out(reading) -> ReadingOut:
    emp = reading.employee
    return ReadingOut(
        id=reading.id,
        tank_id=reading.tank_id,
        reading_at=reading.reading_at,
        physical_stock=reading.physical_stock,
        dip_value=reading.dip_value,
        employee_id=reading.employee_id,
        employee_name=f"{emp.first_name} {emp.last_name}" if emp else "",
        remarks=reading.remarks,
    )


# --- lookups ------------------------------------------------------------------
def _require(services: Services, user_id: str, permission: Permission) -> None:
    if not services.auth.check_permission(user_id, permission.value):
        services.auth.record_permission_denied(user_id, permission.value)
        raise PermissionDeniedError(permission.value)


@router.get("/lookups/fuels", response_model=list[FuelOut])
def list_fuels(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """Qt's Add Tank dialog reads FuelRepository.list_active() directly with no
    check, but only shows that dialog to INVENTORY_MANAGE users - same gate here."""
    _require(services, user.id, Permission.INVENTORY_MANAGE)
    return [FuelOut(id=f.id, fuel_type=f.fuel_type) for f in services.fuel_repo.list_active()]


@router.get("/lookups/employees", response_model=list[EmployeeOut])
def list_employees(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """Same call the Qt reading dialog makes: EmployeeService.list_employees (EMPLOYEE_VIEW)."""
    return [
        EmployeeOut(id=e.id, employee_code=e.employee_code, first_name=e.first_name, last_name=e.last_name)
        for e in services.employees.list_employees(user.id)
    ]


# --- tanks --------------------------------------------------------------------
@router.get("/tanks", response_model=list[TankOut])
def list_tanks(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [tank_out(t, services, user.id) for t in services.tanks.list_tanks(user.id)]


@router.get("/tanks/recent-transactions", response_model=list[TransactionOut])
def recent_transactions(
    limit: int = Query(default=8, ge=1, le=100),
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
):
    return [transaction_out(t) for t in services.tanks.list_recent_transactions(user.id, limit=limit)]


@router.post("/tanks", response_model=TankOut, status_code=201)
def create_tank(body: TankCreateIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    data = TankCreate(**body.model_dump())
    return tank_out(services.tanks.create_tank(user.id, data))


@router.get("/tanks/{tank_id}", response_model=TankOut)
def get_tank(tank_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return tank_out(services.tanks.get_tank(user.id, tank_id), services, user.id)


@router.post("/tanks/{tank_id}/status", response_model=TankOut)
def set_status(
    tank_id: str, body: TankStatusIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return tank_out(services.tanks.set_tank_status(user.id, tank_id, body.status, body.reason))


@router.get("/tanks/{tank_id}/transactions", response_model=list[TransactionOut])
def list_transactions(tank_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [transaction_out(t) for t in services.tanks.list_transactions(user.id, tank_id)]


@router.post("/tanks/{tank_id}/transactions", response_model=TransactionOut, status_code=201)
def record_transaction(
    tank_id: str, body: TransactionIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    data = TankTransactionCreate(quantity=body.quantity, reference=body.reference, remarks=body.remarks)
    return transaction_out(services.tanks.record_transaction(user.id, tank_id, body.type_enum(), data))


@router.get("/tanks/{tank_id}/readings", response_model=list[ReadingOut])
def list_readings(tank_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [reading_out(r) for r in services.tanks.list_readings(user.id, tank_id)]


@router.post("/tanks/{tank_id}/readings", response_model=ReadingOut, status_code=201)
def record_reading(
    tank_id: str, body: ReadingIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    data = TankReadingCreate(**body.model_dump())
    return reading_out(services.tanks.record_reading(user.id, tank_id, data))


@router.get("/tanks/{tank_id}/reconciliations", response_model=list[ReconciliationOut])
def list_reconciliations(tank_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [ReconciliationOut.model_validate(r) for r in services.tanks.list_reconciliations(user.id, tank_id)]


@router.post("/tanks/{tank_id}/reconciliations", response_model=ReconciliationOut, status_code=201)
def perform_reconciliation(
    tank_id: str, body: ReconcileIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    data = ReconciliationPerform(**body.model_dump())
    return ReconciliationOut.model_validate(services.tanks.perform_reconciliation(user.id, tank_id, data))


class DipChartRowIn(In):
    dip_cm: str
    litres: str


class DipChartIn(In):
    rows: list[DipChartRowIn]


class DipChartRowOut(Out):
    dip_cm: str
    litres: str


@router.get("/tanks/{tank_id}/dip-chart", response_model=list[DipChartRowOut])
def get_dip_chart(tank_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [DipChartRowOut(dip_cm=f"{p.dip_cm:.1f}", litres=f"{p.litres:.3f}") for p in services.tank_dip_charts.get(user.id, tank_id)]


@router.put("/tanks/{tank_id}/dip-chart", response_model=list[DipChartRowOut])
def set_dip_chart(tank_id: str, body: DipChartIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """Replace the tank's dip chart (the old rows stay on record, voided). A CSV is read in the browser and arrives here as rows."""
    made = services.tank_dip_charts.set_chart(user.id, tank_id, [(r.dip_cm, r.litres) for r in body.rows])
    return [DipChartRowOut(dip_cm=f"{p.dip_cm:.1f}", litres=f"{p.litres:.3f}") for p in made]
