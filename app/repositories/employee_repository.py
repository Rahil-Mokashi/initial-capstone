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

    def list_all(self) -> List[Employee]:
        return self._session.query(Employee).filter_by(is_deleted=False).all()

    def list_active(self) -> List[Employee]:
        return self._session.query(Employee).filter_by(is_deleted=False, status="active").all()

    def next_employee_code(self) -> str:
        """Generate the next sequential employee code (EMP-0001, EMP-0002, ...).

        Safe for a single-user offline desktop app; employee rows are never
        hard-deleted so the count never goes backwards.
        """
        count = self._session.query(func.count(Employee.id)).scalar() or 0
        return f"EMP-{count + 1:04d}"

    def add(self, employee: Employee) -> Employee:
        self._session.add(employee)
        safe_commit(self._session)
        self._session.refresh(employee)
        return employee

    def update(self, employee: Employee) -> Employee:
        safe_commit(self._session)
        self._session.refresh(employee)
        return employee
