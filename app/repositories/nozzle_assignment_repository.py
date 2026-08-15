from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.nozzle_assignment import NozzleAssignment
from app.repositories.base import safe_commit


class NozzleAssignmentRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, assignment_id: str) -> Optional[NozzleAssignment]:
        return self._session.query(NozzleAssignment).filter_by(id=assignment_id).first()

    def list_for_shift(self, shift_id: str) -> List[NozzleAssignment]:
        return self._session.query(NozzleAssignment).filter_by(shift_id=shift_id).all()

    def get_active_for_employee_in_shift(self, shift_id: str, employee_id: str) -> Optional[NozzleAssignment]:
        return (
            self._session.query(NozzleAssignment)
            .filter_by(shift_id=shift_id, employee_id=employee_id, status="active")
            .first()
        )

    def get_active_for_nozzle_in_shift(self, shift_id: str, nozzle_id: str) -> Optional[NozzleAssignment]:
        return (
            self._session.query(NozzleAssignment)
            .filter_by(shift_id=shift_id, nozzle_id=nozzle_id, status="active")
            .first()
        )

    def get_active_for_nozzle(self, nozzle_id: str) -> Optional[NozzleAssignment]:
        """Any active assignment for this nozzle, across all shifts — used to
        block deactivating a nozzle that's currently in use."""
        return self._session.query(NozzleAssignment).filter_by(nozzle_id=nozzle_id, status="active").first()

    def get_active_for_employee(self, employee_id: str) -> Optional[NozzleAssignment]:
        """Any active assignment for this employee, across all shifts — the
        attendant self-service "what am I assigned to right now" lookup."""
        return self._session.query(NozzleAssignment).filter_by(employee_id=employee_id, status="active").first()

    def add(self, assignment: NozzleAssignment) -> NozzleAssignment:
        self._session.add(assignment)
        safe_commit(self._session)
        self._session.refresh(assignment)
        return assignment

    def update(self, assignment: NozzleAssignment) -> NozzleAssignment:
        safe_commit(self._session)
        self._session.refresh(assignment)
        return assignment
