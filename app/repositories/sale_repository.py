from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sale import Sale
from app.repositories.base import safe_commit


class SaleRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, sale_id: str) -> Optional[Sale]:
        return self._session.query(Sale).filter_by(id=sale_id).first()

    def list_all(self) -> List[Sale]:
        return self._session.query(Sale).order_by(Sale.sale_at.desc()).all()

    def list_by_shift(self, shift_id: str) -> List[Sale]:
        return self._session.query(Sale).filter_by(shift_id=shift_id).order_by(Sale.sale_at.desc()).all()

    def list_by_nozzle(self, nozzle_id: str) -> List[Sale]:
        return self._session.query(Sale).filter_by(nozzle_id=nozzle_id).order_by(Sale.sale_at.desc()).all()

    def list_by_customer(self, customer_id: str) -> List[Sale]:
        return self._session.query(Sale).filter_by(customer_id=customer_id).order_by(Sale.sale_at.desc()).all()

    def next_receipt_number(self) -> str:
        """Sequential RCPT-000001, RCPT-000002, ... - safe for a
        single-user offline desktop app; sales are never hard-deleted."""
        count = self._session.query(func.count(Sale.id)).scalar() or 0
        return f"RCPT-{count + 1:06d}"

    def add(self, sale: Sale) -> Sale:
        self._session.add(sale)
        safe_commit(self._session)
        self._session.refresh(sale)
        return sale

    def update(self, sale: Sale) -> Sale:
        safe_commit(self._session)
        self._session.refresh(sale)
        return sale
