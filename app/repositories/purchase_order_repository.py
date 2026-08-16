from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.repositories.base import safe_commit


class PurchaseOrderRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, po_id: str) -> Optional[PurchaseOrder]:
        return self._session.query(PurchaseOrder).filter_by(id=po_id).first()

    def get_by_po_number(self, po_number: str) -> Optional[PurchaseOrder]:
        return self._session.query(PurchaseOrder).filter_by(po_number=po_number).first()

    def list_all(self) -> List[PurchaseOrder]:
        return self._session.query(PurchaseOrder).order_by(PurchaseOrder.order_date.desc()).all()

    def list_by_supplier(self, supplier_id: str) -> List[PurchaseOrder]:
        return (
            self._session.query(PurchaseOrder)
            .filter_by(supplier_id=supplier_id)
            .order_by(PurchaseOrder.order_date.desc())
            .all()
        )

    def next_po_number(self) -> str:
        """Sequential PO-0001, PO-0002, ... - safe for a single-user
        offline desktop app; purchase orders are never hard-deleted."""
        count = self._session.query(func.count(PurchaseOrder.id)).scalar() or 0
        return f"PO-{count + 1:04d}"

    def add(self, purchase_order: PurchaseOrder) -> PurchaseOrder:
        self._session.add(purchase_order)
        safe_commit(self._session)
        self._session.refresh(purchase_order)
        return purchase_order

    def update(self, purchase_order: PurchaseOrder) -> PurchaseOrder:
        safe_commit(self._session)
        self._session.refresh(purchase_order)
        return purchase_order


class PurchaseOrderItemRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_for_order(self, purchase_order_id: str) -> List[PurchaseOrderItem]:
        return self._session.query(PurchaseOrderItem).filter_by(purchase_order_id=purchase_order_id).all()

    def add(self, item: PurchaseOrderItem) -> PurchaseOrderItem:
        self._session.add(item)
        safe_commit(self._session)
        self._session.refresh(item)
        return item
