"""Procurement: suppliers, purchase orders, the tanker delivery workflow, supplier invoices and payments.
Same ProcurementService calls as app/ui/procurement_window.py."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services, require_permission
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out, VolumeIn, VolumeOut
from api.services import Services
from app.core.constants import Permission
from app.database.base import StatusEnum
from app.schemas.fuel_delivery import FuelDeliveryArrive, FuelDeliveryDipReading
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderItemCreate
from app.schemas.supplier import SupplierCreate
from app.schemas.supplier_invoice import SupplierInvoiceCreate, SupplierPaymentCreate

router = APIRouter(tags=["procurement"])


# ---- responses -----------------------------------------------------------------------
class SupplierOut(Out):
    id: str
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    status: str


class OrderItemOut(Out):
    id: str
    fuel_id: str
    fuel_type: Optional[str] = None
    quantity_ordered: VolumeOut
    rate_per_liter: MoneyOut


class PurchaseOrderOut(Out):
    id: str
    po_number: str
    supplier_id: str
    supplier: Optional[str] = None
    order_date: date
    expected_delivery_date: Optional[date] = None
    status: str
    remarks: Optional[str] = None
    items: list[OrderItemOut]
    # Sum of the item quantities, shown on the "pending deliveries" cards.
    total_quantity: VolumeOut


class DeliveryOut(Out):
    id: str
    purchase_order_id: str
    tank_id: str
    tanker_number: str
    driver_name: Optional[str] = None
    arrived_at: datetime
    status: str
    quality_notes: Optional[str] = None
    pre_dip_value: Optional[VolumeOut] = None
    post_dip_value: Optional[VolumeOut] = None
    quantity_received: Optional[VolumeOut] = None
    rejection_reason: Optional[str] = None
    remarks: Optional[str] = None


class InvoiceOut(Out):
    id: str
    invoice_number: str
    supplier_id: str
    supplier: Optional[str] = None
    purchase_order_id: Optional[str] = None
    invoice_date: date
    due_date: Optional[date] = None
    amount: MoneyOut
    status: str
    remarks: Optional[str] = None


class PaymentOut(Out):
    id: str
    amount: MoneyOut
    payment_date: date
    payment_method: str
    reference: Optional[str] = None
    remarks: Optional[str] = None


class IdLabel(Out):
    id: str
    label: str


class FuelOption(Out):
    id: str
    fuel_type: str


class OrderOptions(Out):
    suppliers: list[IdLabel]
    fuels: list[FuelOption]


class ArrivalOptions(Out):
    tanks: list[IdLabel]
    employees: list[IdLabel]


# ---- requests ------------------------------------------------------------------------
class SupplierIn(In):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None


class SupplierStatusIn(In):
    status: StatusEnum
    reason: OptionalReason


class OrderItemIn(In):
    fuel_id: str
    quantity_ordered: VolumeIn
    rate_per_liter: MoneyIn


class PurchaseOrderIn(In):
    supplier_id: str
    expected_delivery_date: Optional[date] = None
    remarks: Optional[str] = None
    items: list[OrderItemIn]


class CancelIn(In):
    reason: OptionalReason


class ArrivalIn(In):
    tank_id: str
    received_by_employee_id: str
    tanker_number: str
    driver_name: Optional[str] = None
    remarks: Optional[str] = None


class QualityIn(In):
    notes: Optional[str] = None


class DipIn(In):
    dip_value: VolumeIn


class InvoiceIn(In):
    invoice_number: str
    supplier_id: str
    purchase_order_id: Optional[str] = None
    invoice_date: date
    due_date: Optional[date] = None
    amount: MoneyIn
    remarks: Optional[str] = None


class PaymentIn(In):
    amount: MoneyIn
    payment_date: date
    payment_method: str
    reference: Optional[str] = None
    remarks: Optional[str] = None


# ---- mapping -------------------------------------------------------------------------
def supplier_out(s) -> SupplierOut:
    return SupplierOut.model_validate(s)


def po_out(po) -> PurchaseOrderOut:
    return PurchaseOrderOut(
        id=po.id,
        po_number=po.po_number,
        supplier_id=po.supplier_id,
        supplier=po.supplier.name if po.supplier else None,
        order_date=po.order_date,
        expected_delivery_date=po.expected_delivery_date,
        status=po.status,
        remarks=po.remarks,
        items=[
            OrderItemOut(
                id=i.id,
                fuel_id=i.fuel_id,
                fuel_type=i.fuel.fuel_type if i.fuel else None,
                quantity_ordered=i.quantity_ordered,
                rate_per_liter=i.rate_per_liter,
            )
            for i in po.items
        ],
        total_quantity=sum((i.quantity_ordered for i in po.items), Decimal("0")),
    )


def invoice_out(inv) -> InvoiceOut:
    return InvoiceOut(
        id=inv.id,
        invoice_number=inv.invoice_number,
        supplier_id=inv.supplier_id,
        supplier=inv.supplier.name if inv.supplier else None,
        purchase_order_id=inv.purchase_order_id,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        amount=inv.amount,
        status=inv.status,
        remarks=inv.remarks,
    )


# ---- suppliers -----------------------------------------------------------------------
@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [supplier_out(s) for s in services.procurement.list_suppliers(user.id)]


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return supplier_out(services.procurement.create_supplier(user.id, SupplierCreate(**body.model_dump())))


@router.post("/suppliers/{supplier_id}/status", response_model=SupplierOut)
def set_supplier_status(
    supplier_id: str, body: SupplierStatusIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return supplier_out(services.procurement.set_supplier_status(user.id, supplier_id, body.status, body.reason))


# ---- dropdown data (what the Qt dialogs read directly) ------------------------------------
@router.get("/procurement/order-options", response_model=OrderOptions)
def order_options(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    require_permission(services, user.id, Permission.PROCUREMENT_MANAGE)
    return OrderOptions(
        suppliers=[
            IdLabel(id=s.id, label=s.name)
            for s in services.procurement.list_suppliers(user.id)
            if s.status == StatusEnum.ACTIVE.value
        ],
        fuels=[FuelOption(id=f.id, fuel_type=f.fuel_type) for f in services.fuel_repo.list_active()],
    )


@router.get("/procurement/arrival-options", response_model=ArrivalOptions)
def arrival_options(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    require_permission(services, user.id, Permission.PROCUREMENT_MANAGE)
    return ArrivalOptions(
        tanks=[
            IdLabel(id=t.id, label=f"{t.code} ({t.fuel.fuel_type if t.fuel else ''})")
            for t in services.tanks.list_tanks(user.id)
            if t.status == "active"
        ],
        employees=[
            IdLabel(id=e.id, label=f"{e.employee_code} - {e.first_name} {e.last_name}")
            for e in services.employees.list_employees(user.id)
        ],
    )


# ---- purchase orders -----------------------------------------------------------------
@router.get("/purchase-orders", response_model=list[PurchaseOrderOut])
def list_orders(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [po_out(po) for po in services.procurement.list_purchase_orders(user.id)]


@router.post("/purchase-orders", response_model=PurchaseOrderOut, status_code=201)
def create_order(body: PurchaseOrderIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    data = PurchaseOrderCreate(
        supplier_id=body.supplier_id,
        expected_delivery_date=body.expected_delivery_date,
        remarks=body.remarks,
        items=[PurchaseOrderItemCreate(**i.model_dump()) for i in body.items],
    )
    return po_out(services.procurement.create_purchase_order(user.id, data))


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderOut)
def get_order(po_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return po_out(services.procurement.get_purchase_order(user.id, po_id))


@router.post("/purchase-orders/{po_id}/cancel", response_model=PurchaseOrderOut)
def cancel_order(po_id: str, body: CancelIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return po_out(services.procurement.cancel_purchase_order(user.id, po_id, body.reason))


@router.get("/purchase-orders/{po_id}/deliveries", response_model=list[DeliveryOut])
def list_deliveries(po_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.procurement.list_deliveries(user.id, po_id)


@router.post("/purchase-orders/{po_id}/deliveries", response_model=DeliveryOut, status_code=201)
def record_arrival(po_id: str, body: ArrivalIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    data = FuelDeliveryArrive(purchase_order_id=po_id, **body.model_dump())
    return services.procurement.record_delivery_arrival(user.id, data)


# ---- delivery workflow ---------------------------------------------------------------
@router.get("/deliveries/{delivery_id}", response_model=DeliveryOut)
def get_delivery(delivery_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    # Qt's detail dialog reads the delivery through the service's lookup helper; same gate as the list.
    require_permission(services, user.id, Permission.PROCUREMENT_VIEW)
    return services.procurement._get_delivery_or_raise(delivery_id)


@router.post("/deliveries/{delivery_id}/verify-documents", response_model=DeliveryOut)
def verify_documents(delivery_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.procurement.verify_documents(user.id, delivery_id)


@router.post("/deliveries/{delivery_id}/verify-quality", response_model=DeliveryOut)
def verify_quality(delivery_id: str, body: QualityIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.procurement.verify_quality(user.id, delivery_id, (body.notes or "").strip() or None)


@router.post("/deliveries/{delivery_id}/pre-dip", response_model=DeliveryOut)
def pre_dip(delivery_id: str, body: DipIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.procurement.record_pre_dip(user.id, delivery_id, FuelDeliveryDipReading(dip_value=body.dip_value))


@router.post("/deliveries/{delivery_id}/post-dip", response_model=DeliveryOut)
def post_dip(delivery_id: str, body: DipIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.procurement.record_post_dip_and_unload(
        user.id, delivery_id, FuelDeliveryDipReading(dip_value=body.dip_value)
    )


@router.post("/deliveries/{delivery_id}/reject", response_model=DeliveryOut)
def reject(delivery_id: str, body: CancelIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.procurement.reject_delivery(user.id, delivery_id, body.reason)


# ---- invoices and payments -----------------------------------------------------------
@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [invoice_out(i) for i in services.procurement.list_invoices(user.id)]


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(body: InvoiceIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return invoice_out(services.procurement.create_invoice(user.id, SupplierInvoiceCreate(**body.model_dump())))


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    require_permission(services, user.id, Permission.PROCUREMENT_VIEW)
    return invoice_out(services.procurement._get_invoice_or_raise(invoice_id))


@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentOut])
def list_payments(invoice_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.procurement.list_payments(user.id, invoice_id)


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentOut, status_code=201)
def record_payment(invoice_id: str, body: PaymentIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.procurement.record_payment(user.id, invoice_id, SupplierPaymentCreate(**body.model_dump()))
