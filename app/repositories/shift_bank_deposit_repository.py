from typing import List

from sqlalchemy.orm import Session

from app.models.shift_bank_deposit import ShiftBankDeposit
from app.repositories.base import safe_commit


class ShiftBankDepositRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_for_cash_book(self, shift_cash_book_id: str) -> List[ShiftBankDeposit]:
        return (
            self._session.query(ShiftBankDeposit)
            .filter_by(shift_cash_book_id=shift_cash_book_id)
            .order_by(ShiftBankDeposit.recorded_at)
            .all()
        )

    def add(self, deposit: ShiftBankDeposit) -> ShiftBankDeposit:
        self._session.add(deposit)
        safe_commit(self._session)
        self._session.refresh(deposit)
        return deposit
