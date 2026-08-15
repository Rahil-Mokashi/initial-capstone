from sqlalchemy.orm import Session
from app.models.fuel import Fuel
from app.repositories.base import safe_commit


class FuelRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, fuel_id: str):
        return self._session.query(Fuel).filter_by(id=fuel_id, is_deleted=False).first()

    def list_active(self):
        return self._session.query(Fuel).filter_by(is_deleted=False, is_active=True).all()

    def add(self, fuel: Fuel):
        self._session.add(fuel)
        safe_commit(self._session)
        self._session.refresh(fuel)
        return fuel

    def update(self, fuel: Fuel):
        safe_commit(self._session)
        self._session.refresh(fuel)
        return fuel
