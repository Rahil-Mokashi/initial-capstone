"""Fuel prices. Same FuelService calls as app/ui/fuel_price_window.py."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out
from api.services import Services
from app.schemas.fuel import FuelRateChange

router = APIRouter(tags=["fuel-prices"])


class FuelPriceOut(Out):
    id: str
    fuel_type: str
    rate_per_liter: Optional[MoneyOut] = None
    # A zero price is a fuel that cannot be sold; the screen must make that obvious.
    priced: bool


class PriceHistoryOut(Out):
    id: str
    effective_from: datetime
    old_rate_per_liter: Optional[MoneyOut] = None
    new_rate_per_liter: MoneyOut
    reason: str


class RateIn(In):
    new_rate_per_liter: MoneyIn
    reason: OptionalReason


def _out(fuel) -> FuelPriceOut:
    rate = fuel.rate_per_liter
    return FuelPriceOut(
        id=fuel.id,
        fuel_type=fuel.fuel_type,
        rate_per_liter=rate,
        priced=rate is not None and rate > 0,
    )


@router.get("/fuel-prices", response_model=list[FuelPriceOut])
def list_fuel_prices(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [_out(f) for f in services.fuel.list_fuels(user.id)]


@router.get("/fuel-prices/{fuel_id}/history", response_model=list[PriceHistoryOut])
def price_history(fuel_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.fuel.get_price_history(user.id, fuel_id)


@router.post("/fuel-prices/{fuel_id}/rate", response_model=FuelPriceOut)
def set_rate(fuel_id: str, body: RateIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    fuel = services.fuel.set_rate(
        user.id, fuel_id, FuelRateChange(new_rate_per_liter=body.new_rate_per_liter, reason=body.reason)
    )
    return _out(fuel)
