"""Sales, payments, receipts and customers.
Same SaleService / ReportService calls as app/ui/sales_window.py."""

import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyOut, OptionalReason, Out, VolumeIn, VolumeOut
from api.services import Services
from app.core.constants import PaymentMethod, Permission
from app.database.base import StatusEnum
from app.schemas.customer import CustomerCreate
from app.schemas.sale import SaleCreate
from app.services.report_export import build_sale_receipt_html, export_sale_receipt_pdf

router = APIRouter(tags=["sales"])


class SaleOut(Out):
    id: str
    receipt_number: str
    sale_at: datetime
    fuel_type: Optional[str] = None
    nozzle: Optional[str] = None
    customer: Optional[str] = None
    quantity: VolumeOut
    rate_per_liter: MoneyOut
    amount: MoneyOut
    payment_method: str
    status: str
    payment_id: Optional[str] = None
    payment_status: Optional[str] = None


class SalePage(Out):
    total: int
    items: list[SaleOut]


class FuelRevenue(Out):
    fuel_type: str
    quantity: str
    amount: str


class CustomerOut(Out):
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    status: str


class IdLabel(Out):
    id: str
    label: str


class MyAssignment(Out):
    shift_id: str
    nozzle_id: str
    employee_id: str
    nozzle: Optional[str] = None


class SaleOptions(Out):
    """What the Record Sale dialog offers. Someone with shift.view picks shift, nozzle and attendant;
    an attendant sells from their own current assignment instead (as in Qt)."""

    can_pick_freely: bool
    shifts: list[IdLabel]
    nozzles: list[IdLabel]
    employees: list[IdLabel]
    customers: list[IdLabel]
    my_assignment: Optional[MyAssignment] = None


class SaleIn(In):
    shift_id: str
    nozzle_id: str
    employee_id: str
    quantity: VolumeIn
    payment_method: PaymentMethod
    customer_id: Optional[str] = None
    reference_number: Optional[str] = None
    remarks: Optional[str] = None


class SelfSaleIn(In):
    """Attendant path: the server resolves shift, nozzle and attendant from the signed-in user's assignment."""

    quantity: VolumeIn
    payment_method: PaymentMethod
    customer_id: Optional[str] = None
    reference_number: Optional[str] = None
    remarks: Optional[str] = None


class ReasonIn(In):
    reason: OptionalReason


class CustomerIn(In):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class CustomerStatusIn(In):
    status: StatusEnum
    reason: OptionalReason


class PaymentStatusOut(Out):
    id: str
    status: str


class ReceiptOut(Out):
    html: str
    filename: str


def sale_out(services: Services, user_id: str, sale) -> SaleOut:
    payment = services.sales.get_payment_for_sale(user_id, sale.id)
    return SaleOut(
        id=sale.id,
        receipt_number=sale.receipt_number,
        sale_at=sale.sale_at,
        fuel_type=sale.fuel.fuel_type if sale.fuel else None,
        nozzle=sale.nozzle.code if sale.nozzle else None,
        customer=sale.customer.name if sale.customer else None,
        quantity=sale.quantity,
        rate_per_liter=sale.rate_per_liter,
        amount=sale.amount,
        payment_method=sale.payment_method,
        status=sale.status,
        payment_id=payment.id if payment else None,
        payment_status=payment.status if payment else None,
    )


# ---- sales -------------------------------------------------------------------------------
@router.get("/sales", response_model=SalePage)
def list_sales(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
):
    total = services.sales.count_sales(user.id)
    sales = services.sales.list_sales(user.id, limit=limit, offset=offset)
    return SalePage(total=total, items=[sale_out(services, user.id, s) for s in sales])


@router.get("/sales/today-by-fuel", response_model=list[FuelRevenue])
def today_by_fuel(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """The per-fuel revenue cards: ReportService.get_sales_report for today, minus its Total row."""
    report = services.reports.get_sales_report(user.id, date.today(), date.today())
    return [FuelRevenue(fuel_type=r[0], quantity=r[2], amount=r[3]) for r in report.rows if r[0] != "Total"]


@router.get("/sales/options", response_model=SaleOptions)
def sale_options(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    can_pick = services.auth.check_permission(user.id, Permission.SHIFT_VIEW.value)
    customers = [
        IdLabel(id=c.id, label=c.name)
        for c in services.sales.list_customers(user.id)
        if c.status == StatusEnum.ACTIVE.value
    ]
    if can_pick:
        return SaleOptions(
            can_pick_freely=True,
            shifts=[
                IdLabel(id=s.id, label=f"{s.shift_date} {s.shift_label}")
                for s in services.shifts.list_shifts(user.id)
                if s.status == "open"
            ],
            nozzles=[IdLabel(id=n.id, label=n.code) for n in services.shifts.list_active_nozzles(user.id)],
            employees=[
                IdLabel(id=e.id, label=f"{e.employee_code} - {e.first_name} {e.last_name}")
                for e in services.employees.list_employees(user.id)
            ],
            customers=customers,
        )
    a = services.shifts.get_my_active_assignment(user.id)
    mine = (
        MyAssignment(
            shift_id=a.shift_id, nozzle_id=a.nozzle_id, employee_id=a.employee_id, nozzle=a.nozzle.code if a.nozzle else None
        )
        if a
        else None
    )
    return SaleOptions(
        can_pick_freely=False, shifts=[], nozzles=[], employees=[], customers=customers, my_assignment=mine
    )


@router.post("/sales", response_model=SaleOut, status_code=201)
def create_sale(body: SaleIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    sale = services.sales.create_sale(user.id, SaleCreate(**body.model_dump()))
    return sale_out(services, user.id, sale)


@router.post("/sales/mine", response_model=SaleOut, status_code=201)
def create_my_sale(body: SelfSaleIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    a = services.shifts.get_my_active_assignment(user.id)
    if a is None:
        raise ValueError("You have no active nozzle assignment.")
    data = SaleCreate(shift_id=a.shift_id, nozzle_id=a.nozzle_id, employee_id=a.employee_id, **body.model_dump())
    return sale_out(services, user.id, services.sales.create_sale(user.id, data))


@router.post("/sales/{sale_id}/cancel", response_model=SaleOut)
def cancel_sale(sale_id: str, body: ReasonIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return sale_out(services, user.id, services.sales.cancel_sale(user.id, sale_id, body.reason))


@router.get("/sales/{sale_id}/receipt", response_model=ReceiptOut)
def receipt_html(sale_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    sale = services.sales.get_sale(user.id, sale_id)
    payment = services.sales.get_payment_for_sale(user.id, sale_id)
    return ReceiptOut(html=build_sale_receipt_html(sale, payment), filename=f"receipt_{sale.receipt_number}.pdf")


@router.get("/sales/{sale_id}/receipt.pdf")
def receipt_pdf(sale_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    sale = services.sales.get_sale(user.id, sale_id)
    payment = services.sales.get_payment_for_sale(user.id, sale_id)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        export_sale_receipt_pdf(sale, payment, path)
        with open(path, "rb") as f:
            data = f.read()
    finally:
        os.remove(path)
    return Response(content=data, media_type="application/pdf")


@router.post("/payments/{payment_id}/mark-failed", response_model=PaymentStatusOut)
def mark_payment_failed(payment_id: str, body: ReasonIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.sales.mark_payment_failed(user.id, payment_id, body.reason)


@router.post("/payments/{payment_id}/refund", response_model=PaymentStatusOut)
def refund_payment(payment_id: str, body: ReasonIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.sales.refund_payment(user.id, payment_id, body.reason)


# ---- customers ---------------------------------------------------------------------------
@router.get("/customers", response_model=list[CustomerOut])
def list_customers(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.sales.list_customers(user.id)


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.sales.create_customer(user.id, CustomerCreate(**body.model_dump()))


@router.post("/customers/{customer_id}/status", response_model=CustomerOut)
def set_customer_status(
    customer_id: str, body: CustomerStatusIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return services.sales.set_customer_status(user.id, customer_id, body.status, body.reason)
