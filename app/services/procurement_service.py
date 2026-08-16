"""Procurement service layer (problemstatement.md #12, Phase 10):
Fuel Requirement -> Purchase -> Tanker Arrival -> Document Verification
-> Fuel Quality Verification -> Pre-Dip Reading -> Fuel Unloading ->
Post-Dip Reading -> Inventory Update -> Invoice -> Supplier Payment.

Deliberately depends on TankService (not just TankRepository) for the
dip-reading and receipt-transaction steps: a delivery must move fuel
into a tank through the exact same audited, capacity-checked path every
other receipt does, not a parallel one that could drift from it.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from app.core.constants import (
    FuelDeliveryStatus,
    Permission,
    PurchaseOrderStatus,
    SupplierInvoiceStatus,
    TankTransactionType,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.models.fuel_delivery import FuelDelivery
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice, SupplierPayment
from app.schemas.fuel_delivery import FuelDeliveryArrive, FuelDeliveryDipReading
from app.schemas.purchase_order import PurchaseOrderCreate
from app.schemas.supplier import SupplierCreate
from app.schemas.supplier_invoice import SupplierInvoiceCreate, SupplierPaymentCreate
from app.schemas.tank import TankReadingCreate, TankTransactionCreate


class ProcurementService:
    def __init__(
        self,
        supplier_repo,
        po_repo,
        po_item_repo,
        delivery_repo,
        invoice_repo,
        payment_repo,
        fuel_repo,
        employee_repo,
        tank_service,
        audit_repo,
        auth_service,
    ):
        self._supplier_repo = supplier_repo
        self._po_repo = po_repo
        self._po_item_repo = po_item_repo
        self._delivery_repo = delivery_repo
        self._invoice_repo = invoice_repo
        self._payment_repo = payment_repo
        self._fuel_repo = fuel_repo
        self._employee_repo = employee_repo
        self._tank_service = tank_service
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    # ------------------------------------------------------------------
    # Suppliers
    # ------------------------------------------------------------------

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def create_supplier(self, actor_user_id: str, data: SupplierCreate) -> Supplier:
        if self._supplier_repo.get_by_name(data.name):
            raise ConflictError(f"A supplier named {data.name!r} already exists")

        supplier = Supplier(
            name=data.name,
            contact_person=data.contact_person,
            phone=data.phone,
            email=data.email,
            address=data.address,
            gst_number=data.gst_number,
            status=StatusEnum.ACTIVE.value,
        )
        supplier = self._supplier_repo.add(supplier)
        self._audit_repo.record(
            event_type="supplier_created",
            actor_id=actor_user_id,
            entity_type="Supplier",
            entity_id=supplier.id,
            description=f"Created supplier {data.name}",
        )
        return supplier

    @require_permission(Permission.PROCUREMENT_VIEW.value)
    def list_suppliers(self, actor_user_id: str) -> List[Supplier]:
        return self._supplier_repo.list_all()

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def set_supplier_status(self, actor_user_id: str, supplier_id: str, status: StatusEnum, reason: str) -> Supplier:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to change a supplier's status")

        supplier = self._get_supplier_or_raise(supplier_id)
        old_status = supplier.status
        supplier.status = status.value
        supplier = self._supplier_repo.update(supplier)
        self._audit_repo.record(
            event_type="supplier_status_changed",
            actor_id=actor_user_id,
            entity_type="Supplier",
            entity_id=supplier.id,
            description=reason.strip(),
            old_value=old_status,
            new_value=status.value,
        )
        return supplier

    # ------------------------------------------------------------------
    # Purchase Orders
    # ------------------------------------------------------------------

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def create_purchase_order(self, actor_user_id: str, data: PurchaseOrderCreate) -> PurchaseOrder:
        supplier = self._get_supplier_or_raise(data.supplier_id)
        if supplier.status != StatusEnum.ACTIVE.value:
            raise ConflictError("Cannot raise a purchase order against an inactive supplier")
        for item in data.items:
            if not self._fuel_repo.get_by_id(item.fuel_id):
                raise NotFoundError(f"Fuel type not found: {item.fuel_id}")

        purchase_order = PurchaseOrder(
            po_number=self._po_repo.next_po_number(),
            supplier_id=data.supplier_id,
            expected_delivery_date=data.expected_delivery_date,
            status=PurchaseOrderStatus.PLACED.value,
            created_by_id=actor_user_id,
            remarks=data.remarks,
        )
        purchase_order = self._po_repo.add(purchase_order)

        for item in data.items:
            self._po_item_repo.add(
                PurchaseOrderItem(
                    purchase_order_id=purchase_order.id,
                    fuel_id=item.fuel_id,
                    quantity_ordered=item.quantity_ordered,
                    rate_per_liter=item.rate_per_liter,
                )
            )

        self._audit_repo.record(
            event_type="purchase_order_created",
            actor_id=actor_user_id,
            entity_type="PurchaseOrder",
            entity_id=purchase_order.id,
            description=f"Created {purchase_order.po_number} against supplier {supplier.name} ({len(data.items)} item(s))",
        )
        return purchase_order

    @require_permission(Permission.PROCUREMENT_VIEW.value)
    def list_purchase_orders(self, actor_user_id: str) -> List[PurchaseOrder]:
        return self._po_repo.list_all()

    @require_permission(Permission.PROCUREMENT_VIEW.value)
    def get_purchase_order(self, actor_user_id: str, po_id: str) -> PurchaseOrder:
        return self._get_po_or_raise(po_id)

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def cancel_purchase_order(self, actor_user_id: str, po_id: str, reason: str) -> PurchaseOrder:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to cancel a purchase order")

        purchase_order = self._get_po_or_raise(po_id)
        if purchase_order.status != PurchaseOrderStatus.PLACED.value:
            raise ConflictError(f"Cannot cancel a purchase order with status {purchase_order.status}")

        purchase_order.status = PurchaseOrderStatus.CANCELLED.value
        purchase_order = self._po_repo.update(purchase_order)
        self._audit_repo.record(
            event_type="purchase_order_cancelled",
            actor_id=actor_user_id,
            entity_type="PurchaseOrder",
            entity_id=purchase_order.id,
            description=reason.strip(),
        )
        return purchase_order

    # ------------------------------------------------------------------
    # Fuel Deliveries
    # ------------------------------------------------------------------

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def record_delivery_arrival(self, actor_user_id: str, data: FuelDeliveryArrive) -> FuelDelivery:
        purchase_order = self._get_po_or_raise(data.purchase_order_id)
        if purchase_order.status not in (
            PurchaseOrderStatus.PLACED.value,
            PurchaseOrderStatus.PARTIALLY_DELIVERED.value,
        ):
            raise ConflictError(f"Cannot record a delivery against a purchase order with status {purchase_order.status}")

        tank = self._tank_service.get_tank(actor_user_id, data.tank_id)
        po_fuel_ids = {item.fuel_id for item in purchase_order.items}
        if tank.fuel_id not in po_fuel_ids:
            raise ConflictError("This tank's fuel type does not match any item on the purchase order")

        if not self._employee_repo.get_by_id(data.received_by_employee_id):
            raise NotFoundError(f"Employee not found: {data.received_by_employee_id}")

        delivery = FuelDelivery(
            purchase_order_id=data.purchase_order_id,
            tank_id=data.tank_id,
            received_by_employee_id=data.received_by_employee_id,
            tanker_number=data.tanker_number,
            driver_name=data.driver_name,
            status=FuelDeliveryStatus.ARRIVED.value,
            recorded_by_id=actor_user_id,
            remarks=data.remarks,
        )
        delivery = self._delivery_repo.add(delivery)
        self._audit_repo.record(
            event_type="fuel_delivery_arrived",
            actor_id=actor_user_id,
            entity_type="FuelDelivery",
            entity_id=delivery.id,
            description=f"Tanker {data.tanker_number} arrived for {purchase_order.po_number}",
        )
        return delivery

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def verify_documents(self, actor_user_id: str, delivery_id: str) -> FuelDelivery:
        delivery = self._get_delivery_or_raise(delivery_id)
        self._require_delivery_status(delivery, FuelDeliveryStatus.ARRIVED)

        delivery.document_verified_by_id = actor_user_id
        delivery.document_verified_at = datetime.now(timezone.utc)
        delivery.status = FuelDeliveryStatus.DOCUMENTS_VERIFIED.value
        delivery = self._delivery_repo.update(delivery)
        self._audit_repo.record(
            event_type="fuel_delivery_documents_verified",
            actor_id=actor_user_id,
            entity_type="FuelDelivery",
            entity_id=delivery.id,
            description=f"Documents verified for tanker {delivery.tanker_number}",
        )
        return delivery

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def verify_quality(self, actor_user_id: str, delivery_id: str, notes: Optional[str] = None) -> FuelDelivery:
        delivery = self._get_delivery_or_raise(delivery_id)
        self._require_delivery_status(delivery, FuelDeliveryStatus.DOCUMENTS_VERIFIED)

        delivery.quality_verified_by_id = actor_user_id
        delivery.quality_verified_at = datetime.now(timezone.utc)
        delivery.quality_notes = notes
        delivery.status = FuelDeliveryStatus.QUALITY_VERIFIED.value
        delivery = self._delivery_repo.update(delivery)
        self._audit_repo.record(
            event_type="fuel_delivery_quality_verified",
            actor_id=actor_user_id,
            entity_type="FuelDelivery",
            entity_id=delivery.id,
            description=f"Quality verified for tanker {delivery.tanker_number}",
        )
        return delivery

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def reject_delivery(self, actor_user_id: str, delivery_id: str, reason: str) -> FuelDelivery:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to reject a delivery")

        delivery = self._get_delivery_or_raise(delivery_id)
        if delivery.status not in (
            FuelDeliveryStatus.ARRIVED.value,
            FuelDeliveryStatus.DOCUMENTS_VERIFIED.value,
            FuelDeliveryStatus.QUALITY_VERIFIED.value,
        ):
            raise ConflictError(f"Cannot reject a delivery with status {delivery.status}")

        delivery.status = FuelDeliveryStatus.REJECTED.value
        delivery.rejection_reason = reason.strip()
        delivery = self._delivery_repo.update(delivery)
        self._audit_repo.record(
            event_type="fuel_delivery_rejected",
            actor_id=actor_user_id,
            entity_type="FuelDelivery",
            entity_id=delivery.id,
            description=reason.strip(),
        )
        return delivery

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def record_pre_dip(self, actor_user_id: str, delivery_id: str, data: FuelDeliveryDipReading) -> FuelDelivery:
        delivery = self._get_delivery_or_raise(delivery_id)
        self._require_delivery_status(delivery, FuelDeliveryStatus.QUALITY_VERIFIED)

        reading = self._tank_service.record_reading_as_related_action(
            actor_user_id,
            delivery.tank_id,
            TankReadingCreate(
                employee_id=delivery.received_by_employee_id,
                physical_stock=data.dip_value,
                remarks=f"Pre-dip for delivery {delivery.tanker_number}",
            ),
        )
        delivery.pre_dip_value = data.dip_value
        delivery.pre_dip_reading_id = reading.id
        delivery = self._delivery_repo.update(delivery)
        self._audit_repo.record(
            event_type="fuel_delivery_pre_dip_recorded",
            actor_id=actor_user_id,
            entity_type="FuelDelivery",
            entity_id=delivery.id,
            description=f"Pre-dip {data.dip_value} for tanker {delivery.tanker_number}",
        )
        return delivery

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def record_post_dip_and_unload(
        self, actor_user_id: str, delivery_id: str, data: FuelDeliveryDipReading
    ) -> FuelDelivery:
        """Records the post-unload dip reading and, in the same step,
        creates the real Tank RECEIPT transaction for the delivered
        quantity - moving fuel into the tank through TankService's
        normal, capacity-checked, audited receipt path rather than a
        parallel one."""
        delivery = self._get_delivery_or_raise(delivery_id)
        if delivery.status != FuelDeliveryStatus.QUALITY_VERIFIED.value or delivery.pre_dip_value is None:
            raise ConflictError("A pre-dip reading must be recorded before the post-dip reading")
        if data.dip_value < delivery.pre_dip_value:
            raise ValueError("post-dip reading cannot be less than the pre-dip reading")

        quantity_received = data.dip_value - delivery.pre_dip_value

        reading = self._tank_service.record_reading_as_related_action(
            actor_user_id,
            delivery.tank_id,
            TankReadingCreate(
                employee_id=delivery.received_by_employee_id,
                physical_stock=data.dip_value,
                remarks=f"Post-dip for delivery {delivery.tanker_number}",
            ),
        )
        transaction = self._tank_service.record_transaction_as_related_action(
            actor_user_id,
            delivery.tank_id,
            TankTransactionType.RECEIPT,
            TankTransactionCreate(
                quantity=quantity_received,
                reference=delivery.tanker_number,
                remarks=f"Delivery for {delivery.purchase_order.po_number}",
            ),
        )

        delivery.post_dip_value = data.dip_value
        delivery.post_dip_reading_id = reading.id
        delivery.quantity_received = quantity_received
        delivery.tank_transaction_id = transaction.id
        delivery.status = FuelDeliveryStatus.UNLOADED.value
        delivery = self._delivery_repo.update(delivery)

        self._refresh_purchase_order_status(delivery.purchase_order)

        self._audit_repo.record(
            event_type="fuel_delivery_unloaded",
            actor_id=actor_user_id,
            entity_type="FuelDelivery",
            entity_id=delivery.id,
            description=f"Unloaded {quantity_received} from tanker {delivery.tanker_number} into tank {delivery.tank.code}",
        )
        return delivery

    @require_permission(Permission.PROCUREMENT_VIEW.value)
    def list_deliveries(self, actor_user_id: str, purchase_order_id: str) -> List[FuelDelivery]:
        return self._delivery_repo.list_by_purchase_order(purchase_order_id)

    def _refresh_purchase_order_status(self, purchase_order: PurchaseOrder) -> None:
        """A PO is DELIVERED once every item's ordered quantity has been
        met by its unloaded deliveries' fuel type, PARTIALLY_DELIVERED
        otherwise. Recomputed from scratch each time rather than
        incremented, so it can never drift out of sync."""
        deliveries = self._delivery_repo.list_by_purchase_order(purchase_order.id)
        received_by_fuel: dict = {}
        for delivery in deliveries:
            if delivery.status != FuelDeliveryStatus.UNLOADED.value:
                continue
            fuel_id = delivery.tank.fuel_id
            received_by_fuel[fuel_id] = received_by_fuel.get(fuel_id, Decimal("0")) + delivery.quantity_received

        fully_delivered = all(
            received_by_fuel.get(item.fuel_id, Decimal("0")) >= item.quantity_ordered for item in purchase_order.items
        )
        purchase_order.status = (
            PurchaseOrderStatus.DELIVERED.value if fully_delivered else PurchaseOrderStatus.PARTIALLY_DELIVERED.value
        )
        self._po_repo.update(purchase_order)

    # ------------------------------------------------------------------
    # Supplier Invoices & Payments
    # ------------------------------------------------------------------

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def create_invoice(self, actor_user_id: str, data: SupplierInvoiceCreate) -> SupplierInvoice:
        self._get_supplier_or_raise(data.supplier_id)
        if data.purchase_order_id:
            self._get_po_or_raise(data.purchase_order_id)

        invoice = SupplierInvoice(
            invoice_number=data.invoice_number,
            supplier_id=data.supplier_id,
            purchase_order_id=data.purchase_order_id,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            amount=data.amount,
            status=SupplierInvoiceStatus.UNPAID.value,
            recorded_by_id=actor_user_id,
            remarks=data.remarks,
        )
        invoice = self._invoice_repo.add(invoice)
        self._audit_repo.record(
            event_type="supplier_invoice_created",
            actor_id=actor_user_id,
            entity_type="SupplierInvoice",
            entity_id=invoice.id,
            description=f"Recorded invoice {data.invoice_number} for {data.amount}",
        )
        return invoice

    @require_permission(Permission.PROCUREMENT_VIEW.value)
    def list_invoices(self, actor_user_id: str) -> List[SupplierInvoice]:
        return self._invoice_repo.list_all()

    @require_permission(Permission.PROCUREMENT_MANAGE.value)
    def record_payment(self, actor_user_id: str, invoice_id: str, data: SupplierPaymentCreate) -> SupplierPayment:
        invoice = self._get_invoice_or_raise(invoice_id)
        if invoice.status == SupplierInvoiceStatus.PAID.value:
            raise ConflictError("This invoice is already fully paid")

        already_paid = self._payment_repo.sum_for_invoice(invoice_id)
        outstanding = invoice.amount - already_paid
        if data.amount > outstanding:
            raise ConflictError(f"Payment of {data.amount} would exceed the outstanding balance of {outstanding}")

        payment = SupplierPayment(
            supplier_invoice_id=invoice_id,
            amount=data.amount,
            payment_date=data.payment_date,
            payment_method=data.payment_method,
            reference=data.reference,
            recorded_by_id=actor_user_id,
            remarks=data.remarks,
        )
        payment = self._payment_repo.add(payment)

        new_total_paid = already_paid + data.amount
        invoice.status = (
            SupplierInvoiceStatus.PAID.value
            if new_total_paid >= invoice.amount
            else SupplierInvoiceStatus.PARTIALLY_PAID.value
        )
        self._invoice_repo.update(invoice)

        self._audit_repo.record(
            event_type="supplier_payment_recorded",
            actor_id=actor_user_id,
            entity_type="SupplierPayment",
            entity_id=payment.id,
            description=f"Paid {data.amount} against invoice {invoice.invoice_number}",
        )
        return payment

    @require_permission(Permission.PROCUREMENT_VIEW.value)
    def list_payments(self, actor_user_id: str, invoice_id: str) -> List[SupplierPayment]:
        return self._payment_repo.list_for_invoice(invoice_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_supplier_or_raise(self, supplier_id: str) -> Supplier:
        supplier = self._supplier_repo.get_by_id(supplier_id)
        if not supplier:
            raise NotFoundError(f"Supplier not found: {supplier_id}")
        return supplier

    def _get_po_or_raise(self, po_id: str) -> PurchaseOrder:
        purchase_order = self._po_repo.get_by_id(po_id)
        if not purchase_order:
            raise NotFoundError(f"Purchase order not found: {po_id}")
        return purchase_order

    def _get_delivery_or_raise(self, delivery_id: str) -> FuelDelivery:
        delivery = self._delivery_repo.get_by_id(delivery_id)
        if not delivery:
            raise NotFoundError(f"Fuel delivery not found: {delivery_id}")
        return delivery

    def _get_invoice_or_raise(self, invoice_id: str) -> SupplierInvoice:
        invoice = self._invoice_repo.get_by_id(invoice_id)
        if not invoice:
            raise NotFoundError(f"Supplier invoice not found: {invoice_id}")
        return invoice

    @staticmethod
    def _require_delivery_status(delivery: FuelDelivery, expected: FuelDeliveryStatus) -> None:
        if delivery.status != expected.value:
            raise ConflictError(f"Expected delivery status {expected.value!r}, got {delivery.status!r}")
