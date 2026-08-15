from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.shift import Shift
from app.repositories.base import safe_commit


class ShiftRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, shift_id: str) -> Optional[Shift]:
        return self._session.query(Shift).filter_by(id=shift_id).first()

    def get_by_date_and_label(self, shift_date: date, shift_label: str) -> Optional[Shift]:
        return self._session.query(Shift).filter_by(shift_date=shift_date, shift_label=shift_label).first()

    def list_for_date_range(self, date_from: Optional[date] = None, date_to: Optional[date] = None) -> List[Shift]:
        query = self._session.query(Shift)
        if date_from:
            query = query.filter(Shift.shift_date >= date_from)
        if date_to:
            query = query.filter(Shift.shift_date <= date_to)
        return query.order_by(Shift.shift_date.desc()).all()

    def add(self, shift: Shift) -> Shift:
        self._session.add(shift)
        safe_commit(self._session)
        self._session.refresh(shift)
        return shift

    def update(self, shift: Shift) -> Shift:
        safe_commit(self._session)
        self._session.refresh(shift)
        return shift
