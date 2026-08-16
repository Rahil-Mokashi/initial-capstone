from typing import List, Optional

from sqlalchemy.orm import Session

from app.database.base import StatusEnum
from app.models.customer import Customer
from app.repositories.base import safe_commit


class CustomerRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, customer_id: str) -> Optional[Customer]:
        return self._session.query(Customer).filter_by(id=customer_id, is_deleted=False).first()

    def get_by_name(self, name: str) -> Optional[Customer]:
        return self._session.query(Customer).filter_by(name=name, is_deleted=False).first()

    def list_all(self) -> List[Customer]:
        return self._session.query(Customer).filter_by(is_deleted=False).all()

    def list_active(self) -> List[Customer]:
        return self._session.query(Customer).filter_by(is_deleted=False, status=StatusEnum.ACTIVE.value).all()

    def add(self, customer: Customer) -> Customer:
        self._session.add(customer)
        safe_commit(self._session)
        self._session.refresh(customer)
        return customer

    def update(self, customer: Customer) -> Customer:
        safe_commit(self._session)
        self._session.refresh(customer)
        return customer
