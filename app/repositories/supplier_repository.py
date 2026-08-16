from typing import List, Optional

from sqlalchemy.orm import Session

from app.database.base import StatusEnum
from app.models.supplier import Supplier
from app.repositories.base import safe_commit


class SupplierRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, supplier_id: str) -> Optional[Supplier]:
        return self._session.query(Supplier).filter_by(id=supplier_id, is_deleted=False).first()

    def get_by_name(self, name: str) -> Optional[Supplier]:
        return self._session.query(Supplier).filter_by(name=name, is_deleted=False).first()

    def list_all(self) -> List[Supplier]:
        return self._session.query(Supplier).filter_by(is_deleted=False).all()

    def list_active(self) -> List[Supplier]:
        return self._session.query(Supplier).filter_by(is_deleted=False, status=StatusEnum.ACTIVE.value).all()

    def add(self, supplier: Supplier) -> Supplier:
        self._session.add(supplier)
        safe_commit(self._session)
        self._session.refresh(supplier)
        return supplier

    def update(self, supplier: Supplier) -> Supplier:
        safe_commit(self._session)
        self._session.refresh(supplier)
        return supplier
