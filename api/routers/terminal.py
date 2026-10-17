"""Terminal (quick bill). Builds exactly the SaleCreate that app/ui/terminal_window.py builds and calls the
same SaleService.create_sale; only the entry screen differs from the full Sales screen."""

from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.routers.sales import IdLabel, SaleOut, sale_out
from api.schemas import CreditOverrideIn, In, MoneyIn, MoneyOut, Out, VolumeIn
from api.services import Services
from app.core.constants import PaymentMethod, Permission
from app.database.base import StatusEnum
from app.schemas.sale import SaleCreate

router = APIRouter(tags=["terminal"])


class TerminalNozzle(Out):
    id: str
    code: str
    fuel_type: Optional[str] = None
    # None when the fuel has no selling price yet (the screen then says so and refuses to sell).
    rate_per_liter: Optional[MoneyOut] = None


class TerminalAssignment(Out):
    shift_id: str
    employee_id: str
    nozzle: TerminalNozzle


class TerminalContext(Out):
    can_pick_freely: bool
    shifts: list[IdLabel]
    employees: list[IdLabel]
    nozzles: list[TerminalNozzle]
    customers: list[IdLabel]
    my_assignment: Optional[TerminalAssignment] = None


class TerminalSaleIn(In):
    """`mode` says what `value` is: rupees (the quantity is value / rate, as Qt does) or litres."""

    mode: Literal["amount", "litres"]
    value: MoneyIn
    payment_method: PaymentMethod
    customer_id: Optional[str] = None
    reference_number: Optional[str] = None
    remarks: Optional[str] = None
    vehicle_number: str  # required on every Terminal sale
    # Free-pick users (shift.view) choose these; an attendant's come from their own assignment.
    shift_id: Optional[str] = None
    nozzle_id: Optional[str] = None
    employee_id: Optional[str] = None
    # An owner allowing this credit sale past the customer's limit (V-14); only used when the limit is passed.
    credit_override: Optional[CreditOverrideIn] = None


def _nozzle(n) -> TerminalNozzle:
    rate = n.fuel.rate_per_liter if n.fuel else None
    priced = rate is not None and Decimal(str(rate)) > 0
    return TerminalNozzle(
        id=n.id, code=n.code, fuel_type=n.fuel.fuel_type if n.fuel else None, rate_per_liter=rate if priced else None
    )


@router.get("/terminal/context", response_model=TerminalContext)
def terminal_context(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    customers = [
        IdLabel(id=c.id, label=c.name)
        for c in services.sales.list_customers(user.id)
        if c.status == StatusEnum.ACTIVE.value
    ]
    if not services.auth.check_permission(user.id, Permission.SHIFT_VIEW.value):
        services.require_attendant_sales(user.id)
    if services.auth.check_permission(user.id, Permission.SHIFT_VIEW.value):
        return TerminalContext(
            can_pick_freely=True,
            shifts=[
                IdLabel(id=s.id, label=f"{s.shift_date} {s.shift_label}")
                for s in services.shifts.list_shifts(user.id)
                if s.status == "open"
            ],
            employees=[
                IdLabel(id=e.id, label=f"{e.employee_code} - {e.first_name} {e.last_name}")
                for e in services.employees.list_employees(user.id)
            ],
            nozzles=[_nozzle(n) for n in services.shifts.list_active_nozzles(user.id)],
            customers=customers,
        )
    a = services.shifts.get_my_active_assignment(user.id)
    return TerminalContext(
        can_pick_freely=False,
        shifts=[],
        employees=[],
        nozzles=[],
        customers=customers,
        my_assignment=(
            TerminalAssignment(shift_id=a.shift_id, employee_id=a.employee_id, nozzle=_nozzle(a.nozzle)) if a and a.nozzle else None
        ),
    )


@router.post("/terminal/sales", response_model=SaleOut, status_code=201)
def terminal_sale(body: TerminalSaleIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    if services.auth.check_permission(user.id, Permission.SHIFT_VIEW.value):
        if not (body.shift_id and body.nozzle_id and body.employee_id):
            raise ValueError("Choose a shift, a nozzle and an attendant first.")
        shift_id, nozzle_id, employee_id = body.shift_id, body.nozzle_id, body.employee_id
    else:
        services.require_attendant_sales(user.id)
        a = services.shifts.get_my_active_assignment(user.id)
        if a is None:
            raise ValueError("You have no active nozzle assignment.")
        shift_id, nozzle_id, employee_id = a.shift_id, a.nozzle_id, a.employee_id

    nozzle = services.nozzle_repo.get_by_id(nozzle_id)
    rate = Decimal(str(nozzle.fuel.rate_per_liter)) if nozzle and nozzle.fuel and nozzle.fuel.rate_per_liter else Decimal("0")
    if rate <= 0:
        raise ValueError("This fuel has no selling price set - a manager must set it before this can be sold.")

    value = Decimal(body.value)
    quantity = value / rate if body.mode == "amount" else value  # full precision, as Qt passes it
    data = SaleCreate(
        shift_id=shift_id,
        nozzle_id=nozzle_id,
        employee_id=employee_id,
        quantity=quantity,
        payment_method=body.payment_method,
        customer_id=body.customer_id,
        reference_number=body.reference_number,
        remarks=body.remarks,
        vehicle_number=body.vehicle_number,
    )
    return sale_out(services, user.id, services.create_credit_aware_sale(user.id, data, body.credit_override))
