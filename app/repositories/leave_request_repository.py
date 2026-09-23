from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.constants import LeaveRequestStatus
from app.models.leave_request import LeaveRequest
from app.repositories.base import safe_commit


class LeaveRequestRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, leave_request_id: str) -> Optional[LeaveRequest]:
        return self._session.query(LeaveRequest).filter_by(id=leave_request_id).first()

    def list_all(self) -> List[LeaveRequest]:
        return self._session.query(LeaveRequest).order_by(LeaveRequest.date_from.desc()).all()

    def list_for_employee(self, employee_id: str) -> List[LeaveRequest]:
        return (
            self._session.query(LeaveRequest)
            .filter_by(employee_id=employee_id)
            .order_by(LeaveRequest.date_from.desc())
            .all()
        )

    def list_overlapping_active(self, employee_id: str, date_from: date, date_to: date) -> List[LeaveRequest]:
        """Every PENDING or APPROVED request for this employee whose date
        range overlaps [date_from, date_to] - used to reject a duplicate
        or double-booked request before it reaches an approver, the same
        "duplicate active assignment" rule NozzleAssignment already
        enforces, applied here instead of invented fresh."""
        active_statuses = (LeaveRequestStatus.PENDING.value, LeaveRequestStatus.APPROVED.value)
        return (
            self._session.query(LeaveRequest)
            .filter(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status.in_(active_statuses),
                LeaveRequest.date_from <= date_to,
                LeaveRequest.date_to >= date_from,
            )
            .all()
        )

    def add(self, leave_request: LeaveRequest) -> LeaveRequest:
        self._session.add(leave_request)
        safe_commit(self._session)
        self._session.refresh(leave_request)
        return leave_request

    def update(self, leave_request: LeaveRequest) -> LeaveRequest:
        safe_commit(self._session)
        self._session.refresh(leave_request)
        return leave_request
