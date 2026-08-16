from typing import List

from sqlalchemy.orm import Session

from app.models.customer_payment import CustomerPayment
from app.repositories.base import safe_commit


class CustomerPaymentRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_all(self) -> List[CustomerPayment]:
        return self._session.query(CustomerPayment).order_by(CustomerPayment.payment_date.desc()).all()

    def list_for_customer(self, customer_id: str) -> List[CustomerPayment]:
        return (
            self._session.query(CustomerPayment)
            .filter_by(customer_id=customer_id)
            .order_by(CustomerPayment.payment_date.desc())
            .all()
        )

    def add(self, payment: CustomerPayment) -> CustomerPayment:
        self._session.add(payment)
        safe_commit(self._session)
        self._session.refresh(payment)
        return payment
