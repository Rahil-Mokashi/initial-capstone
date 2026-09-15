from typing import List

from sqlalchemy.orm import Session

from app.models.employee_cash_shortage import EmployeeShortageRecovery
from app.repositories.base import safe_commit


class EmployeeShortageRecoveryRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_for_shortage(self, employee_cash_shortage_id: str) -> List[EmployeeShortageRecovery]:
        return (
            self._session.query(EmployeeShortageRecovery)
            .filter_by(employee_cash_shortage_id=employee_cash_shortage_id)
            .order_by(EmployeeShortageRecovery.recorded_at)
            .all()
        )

    def list_for_cash_book(self, shift_cash_book_id: str) -> List[EmployeeShortageRecovery]:
        return (
            self._session.query(EmployeeShortageRecovery)
            .filter_by(shift_cash_book_id=shift_cash_book_id)
            .order_by(EmployeeShortageRecovery.recorded_at)
            .all()
        )

    def add(self, recovery: EmployeeShortageRecovery) -> EmployeeShortageRecovery:
        self._session.add(recovery)
        safe_commit(self._session)
        self._session.refresh(recovery)
        return recovery
