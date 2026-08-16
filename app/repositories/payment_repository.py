from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.payment import Payment
from app.repositories.base import safe_commit


class PaymentRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, payment_id: str) -> Optional[Payment]:
        return self._session.query(Payment).filter_by(id=payment_id).first()

    def get_by_sale_id(self, sale_id: str) -> Optional[Payment]:
        return self._session.query(Payment).filter_by(sale_id=sale_id).first()

    def list_all(self) -> List[Payment]:
        return self._session.query(Payment).order_by(Payment.payment_at.desc()).all()

    def add(self, payment: Payment) -> Payment:
        self._session.add(payment)
        safe_commit(self._session)
        self._session.refresh(payment)
        return payment

    def update(self, payment: Payment) -> Payment:
        safe_commit(self._session)
        self._session.refresh(payment)
        return payment
