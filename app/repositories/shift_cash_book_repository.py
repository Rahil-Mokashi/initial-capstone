from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.shift_cash_book import ShiftCashBook
from app.repositories.base import safe_commit


class ShiftCashBookRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, cash_book_id: str) -> Optional[ShiftCashBook]:
        return self._session.query(ShiftCashBook).filter_by(id=cash_book_id).first()

    def get_by_shift_id(self, shift_id: str) -> Optional[ShiftCashBook]:
        return self._session.query(ShiftCashBook).filter_by(shift_id=shift_id).first()

    def list_all(self) -> List[ShiftCashBook]:
        return self._session.query(ShiftCashBook).order_by(ShiftCashBook.recorded_at.desc()).all()

    def add(self, cash_book: ShiftCashBook) -> ShiftCashBook:
        self._session.add(cash_book)
        safe_commit(self._session)
        self._session.refresh(cash_book)
        return cash_book
