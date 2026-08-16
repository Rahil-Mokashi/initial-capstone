from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.supplier_invoice import SupplierInvoice, SupplierPayment
from app.repositories.base import safe_commit


class SupplierInvoiceRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, invoice_id: str) -> Optional[SupplierInvoice]:
        return self._session.query(SupplierInvoice).filter_by(id=invoice_id).first()

    def list_all(self) -> List[SupplierInvoice]:
        return self._session.query(SupplierInvoice).order_by(SupplierInvoice.invoice_date.desc()).all()

    def list_by_supplier(self, supplier_id: str) -> List[SupplierInvoice]:
        return (
            self._session.query(SupplierInvoice)
            .filter_by(supplier_id=supplier_id)
            .order_by(SupplierInvoice.invoice_date.desc())
            .all()
        )

    def add(self, invoice: SupplierInvoice) -> SupplierInvoice:
        self._session.add(invoice)
        safe_commit(self._session)
        self._session.refresh(invoice)
        return invoice

    def update(self, invoice: SupplierInvoice) -> SupplierInvoice:
        safe_commit(self._session)
        self._session.refresh(invoice)
        return invoice


class SupplierPaymentRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_for_invoice(self, supplier_invoice_id: str) -> List[SupplierPayment]:
        return (
            self._session.query(SupplierPayment)
            .filter_by(supplier_invoice_id=supplier_invoice_id)
            .order_by(SupplierPayment.payment_date.desc())
            .all()
        )

    def sum_for_invoice(self, supplier_invoice_id: str) -> Decimal:
        payments = self.list_for_invoice(supplier_invoice_id)
        return sum((payment.amount for payment in payments), Decimal("0"))

    def add(self, payment: SupplierPayment) -> SupplierPayment:
        self._session.add(payment)
        safe_commit(self._session)
        self._session.refresh(payment)
        return payment
