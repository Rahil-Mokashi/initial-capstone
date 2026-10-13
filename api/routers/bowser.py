"""The bowser van: Stock Transfers in, delivery bills out, its own meter, and the day as the report shows it."""

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out, VolumeIn, VolumeOut
from api.services import Services
from app.services.daily_report_service import report_to_dict

router = APIRouter(tags=["bowser"])


class BowserDayOut(Out):
    day: date
    day_report: dict[str, Any]


class TransferIn(In):
    shift_id: str
    nozzle_id: str
    employee_id: str
    litres: VolumeIn


class TransferOut(Out):
    id: str
    litres: VolumeOut
    rate: MoneyOut
    amount: MoneyOut
    sale_id: str


class BillIn(In):
    bill_no: str
    bill_date: date
    customer_id: str
    quantity: VolumeIn
    rate: MoneyIn
    transport: MoneyIn = "0"
    vehicle_no: Optional[str] = None
    slip_no: Optional[str] = None
    shift_id: Optional[str] = None


class BowserBillOut(Out):
    id: str
    bill_no: str
    quantity: VolumeOut
    rate: MoneyOut
    amount: MoneyOut
    transport: MoneyOut
    total: MoneyOut
    status: str


class BowserVoidIn(In):
    reason: OptionalReason


class MeterIn(In):
    day: date
    start_reading: VolumeIn
    testing: VolumeIn = "0"
    end_reading: VolumeIn


class MeterOut(Out):
    id: str
    start_reading: VolumeOut
    testing: VolumeOut
    end_reading: VolumeOut


class OpeningIn(In):
    day: date
    litres: VolumeIn
    rupees: MoneyIn
    reason: OptionalReason


class OpeningOut(Out):
    id: str
    litres: VolumeOut
    rupees: MoneyOut


@router.get("/bowser/day", response_model=BowserDayOut)
def bowser_day(day: Optional[date] = None, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    day = day or date.today()
    return BowserDayOut(day=day, day_report=report_to_dict(services.bowser.day(user.id, day)))


@router.post("/bowser/transfers", response_model=TransferOut, status_code=201)
def transfer(body: TransferIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return TransferOut.model_validate(
        services.bowser.record_transfer(user.id, body.shift_id, body.nozzle_id, body.employee_id, body.litres)
    )


@router.post("/bowser/bills", response_model=BowserBillOut, status_code=201)
def bill(body: BillIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BowserBillOut.model_validate(services.bowser.record_bill(
        user.id, body.bill_no, body.bill_date, body.customer_id, body.quantity, body.rate, body.transport,
        body.vehicle_no, body.slip_no, body.shift_id,
    ))


@router.post("/bowser/bills/{bill_id}/void", response_model=BowserBillOut)
def void_bill(bill_id: str, body: BowserVoidIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return BowserBillOut.model_validate(services.bowser.void_bill(user.id, bill_id, body.reason))


@router.post("/bowser/meter", response_model=MeterOut, status_code=201)
def meter(body: MeterIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return MeterOut.model_validate(
        services.bowser.record_meter(user.id, body.day, body.start_reading, body.testing, body.end_reading)
    )


@router.post("/bowser/opening", response_model=OpeningOut, status_code=201)
def opening(body: OpeningIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return OpeningOut.model_validate(services.bowser.set_opening(user.id, body.day, body.litres, body.rupees, body.reason))
