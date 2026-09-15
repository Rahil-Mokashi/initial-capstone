from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.nozzle import Nozzle
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

    def sum_testing_volume_for_tank(
        self, tank_id: str, fuel_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> Decimal:
        """Testing volume lives on NozzleAssignment, not TankTransaction
        (TankTransactionType's docstring) - it crosses a nozzle's meter
        but is poured back into the tank, so it's summed here for
        whichever nozzles draw from this tank, for FuelReconciliation's
        informational testing_quantity (never subtracted from expected
        stock - see TankService._perform_reconciliation_impl).

        Includes nozzles with no tank_id set that share this tank's fuel
        - the same single-tank-per-fuel fallback SaleService.
        _resolve_tank_id uses - rather than only exact tank_id matches,
        so a site that hasn't explicitly configured every nozzle's tank
        doesn't silently lose testing visibility. date_from/date_to
        widening mirrors TankTransactionRepository.sum_for_tank_by_type
        for the same reason: a naive local-midnight boundary compared
        against a UTC timestamp drops rows recorded after local midnight
        whenever local time runs ahead of UTC.
        """
        query = (
            self._session.query(NozzleAssignment)
            .join(Nozzle, NozzleAssignment.nozzle_id == Nozzle.id)
            .filter(or_(Nozzle.tank_id == tank_id, and_(Nozzle.tank_id.is_(None), Nozzle.fuel_id == fuel_id)))
        )
        if date_from:
            start_of_day = datetime.combine(date_from, time.min).astimezone(timezone.utc)
            query = query.filter(NozzleAssignment.end_time >= start_of_day)
        if date_to:
            end_of_day = datetime.combine(date_to, time.max).astimezone(timezone.utc)
            query = query.filter(NozzleAssignment.end_time <= end_of_day)
        return sum((a.testing_volume for a in query.all()), Decimal("0"))

    def add(self, assignment: NozzleAssignment) -> NozzleAssignment:
        self._session.add(assignment)
        safe_commit(self._session)
        self._session.refresh(assignment)
        return assignment

    def update(self, assignment: NozzleAssignment) -> NozzleAssignment:
        safe_commit(self._session)
        self._session.refresh(assignment)
        return assignment
