from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.fuel_delivery import FuelDelivery
from app.repositories.base import safe_commit


class FuelDeliveryRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, delivery_id: str) -> Optional[FuelDelivery]:
        return self._session.query(FuelDelivery).filter_by(id=delivery_id).first()

    def list_all(self) -> List[FuelDelivery]:
        return self._session.query(FuelDelivery).order_by(FuelDelivery.arrived_at.desc()).all()

    def list_by_purchase_order(self, purchase_order_id: str) -> List[FuelDelivery]:
        return (
            self._session.query(FuelDelivery)
            .filter_by(purchase_order_id=purchase_order_id)
            .order_by(FuelDelivery.arrived_at.desc())
            .all()
        )

    def add(self, delivery: FuelDelivery) -> FuelDelivery:
        self._session.add(delivery)
        safe_commit(self._session)
        self._session.refresh(delivery)
        return delivery

    def update(self, delivery: FuelDelivery) -> FuelDelivery:
        safe_commit(self._session)
        self._session.refresh(delivery)
        return delivery
