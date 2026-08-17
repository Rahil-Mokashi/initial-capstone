from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.repositories.base import safe_commit


class EmployeeRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, employee_id: str) -> Optional[Employee]:
        return self._session.query(Employee).filter_by(id=employee_id, is_deleted=False).first()

    def get_by_code(self, employee_code: str) -> Optional[Employee]:
        return self._session.query(Employee).filter_by(employee_code=employee_code, is_deleted=False).first()

    def get_by_user_id(self, user_id: str) -> Optional[Employee]:
        return self._session.query(Employee).filter_by(user_id=user_id, is_deleted=False).first()

    def list_all(self) -> List[Employee]:
        return self._session.query(Employee).filter_by(is_deleted=False).all()

    def list_active(self) -> List[Employee]:
        return self._session.query(Employee).filter_by(is_deleted=False, status="active").all()

    def next_employee_code(self) -> str:
        """Generate the next sequential employee code (EMP-0001, EMP-0002, ...).

        Derived from the highest code ever issued rather than a row count,
        for the same reason as SaleRepository.next_receipt_number: a count
        is not a high-water mark, and after a restore from backup it hands
        out codes that already exist. Employee codes are unique, so that
        collision blocks employee creation outright.
        """
        highest = self._session.query(func.max(Employee.employee_code)).scalar()
        if not highest:
            return "EMP-0001"
        try:
            last = int(str(highest).rsplit("-", 1)[1])
        except (IndexError, ValueError):
            last = self._session.query(func.count(Employee.id)).scalar() or 0
        return f"EMP-{last + 1:04d}"

    def add(self, employee: Employee) -> Employee:
        self._session.add(employee)
        safe_commit(self._session)
        self._session.refresh(employee)
        return employee

    def update(self, employee: Employee) -> Employee:
        safe_commit(self._session)
        self._session.refresh(employee)
        return employee
