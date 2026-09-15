from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.employee_cash_shortage import EmployeeCashShortage
from app.repositories.base import safe_commit


class EmployeeCashShortageRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, shortage_id: str) -> Optional[EmployeeCashShortage]:
        return self._session.query(EmployeeCashShortage).filter_by(id=shortage_id).first()

    def get_by_line_id(self, shift_reconciliation_line_id: str) -> Optional[EmployeeCashShortage]:
        return (
            self._session.query(EmployeeCashShortage)
            .filter_by(shift_reconciliation_line_id=shift_reconciliation_line_id)
            .first()
        )

    def list_all(self) -> List[EmployeeCashShortage]:
        return self._session.query(EmployeeCashShortage).order_by(EmployeeCashShortage.recorded_at.desc()).all()

    def list_for_employee(self, employee_id: str) -> List[EmployeeCashShortage]:
        return (
            self._session.query(EmployeeCashShortage)
            .filter_by(employee_id=employee_id)
            .order_by(EmployeeCashShortage.recorded_at.desc())
            .all()
        )

    def add(self, shortage: EmployeeCashShortage) -> EmployeeCashShortage:
        self._session.add(shortage)
        safe_commit(self._session)
        self._session.refresh(shortage)
        return shortage
