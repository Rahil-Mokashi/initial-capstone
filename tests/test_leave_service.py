from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import AttendanceStatus, LeaveRequestStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.employee import Employee
from app.models.role import Role
from app.models.user import User
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.leave_request_repository import LeaveRequestRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.leave_request import LeaveRequestCreate
from app.services.attendance_service import AttendanceService
from app.services.auth_service import AuthService
from app.services.leave_service import LeaveService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_leave.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


def make_user(db_session, role_name: str, username: str) -> User:
    role = db_session.query(Role).filter_by(name=role_name).first()
    user = User(
        username=username, email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"), role=role, is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_id(db_session):
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def manager_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.MANAGER.value, "manager1").id


@pytest.fixture()
def shift_supervisor_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.SHIFT_SUPERVISOR.value, "supervisor1").id


@pytest.fixture()
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def employee_id(db_session):
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add(employee)
    db_session.commit()
    return employee.id


@pytest.fixture()
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def attendance_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return AttendanceService(
        AttendanceRepository(db_session), EmployeeRepository(db_session),
        ShiftRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def leave_service(db_session, auth_service, attendance_service):
    audit_repo = AuditLogRepository(db_session)
    return LeaveService(
        LeaveRequestRepository(db_session), EmployeeRepository(db_session),
        audit_repo, auth_service, attendance_service=attendance_service,
    )


def make_request_data(employee_id, days_from_today=5, span_days=2, reason="Family function"):
    date_from = date.today() + timedelta(days=days_from_today)
    date_to = date_from + timedelta(days=span_days - 1)
    return LeaveRequestCreate(employee_id=employee_id, date_from=date_from, date_to=date_to, reason=reason)


# --------------------------------------------------------------------
# Requesting leave
# --------------------------------------------------------------------

def test_manager_can_request_leave(leave_service, manager_id, employee_id):
    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id))
    assert leave_request.status == LeaveRequestStatus.PENDING.value
    assert leave_request.requested_by_id == manager_id


def test_shift_supervisor_can_request_leave(leave_service, shift_supervisor_id, employee_id):
    leave_request = leave_service.request_leave(shift_supervisor_id, make_request_data(employee_id))
    assert leave_request.status == LeaveRequestStatus.PENDING.value


def test_attendant_cannot_request_leave(leave_service, attendant_id, employee_id):
    with pytest.raises(PermissionDeniedError):
        leave_service.request_leave(attendant_id, make_request_data(employee_id))


def test_request_leave_for_unknown_employee_raises(leave_service, manager_id):
    with pytest.raises(NotFoundError):
        leave_service.request_leave(manager_id, make_request_data("not-a-real-id"))


def test_blank_reason_rejected_at_the_schema_level(employee_id):
    with pytest.raises(Exception):
        LeaveRequestCreate(employee_id=employee_id, date_from=date.today(), date_to=date.today(), reason="   ")


def test_date_from_after_date_to_rejected_at_the_schema_level(employee_id):
    with pytest.raises(Exception):
        LeaveRequestCreate(
            employee_id=employee_id, date_from=date.today() + timedelta(days=2),
            date_to=date.today(), reason="Trip",
        )


def test_overlapping_pending_request_is_rejected(leave_service, manager_id, employee_id):
    leave_service.request_leave(manager_id, make_request_data(employee_id, days_from_today=5, span_days=3))
    with pytest.raises(ConflictError):
        # Overlaps the first request's middle day.
        leave_service.request_leave(manager_id, make_request_data(employee_id, days_from_today=6, span_days=1))


def test_non_overlapping_request_is_allowed(leave_service, manager_id, employee_id):
    leave_service.request_leave(manager_id, make_request_data(employee_id, days_from_today=5, span_days=2))
    second = leave_service.request_leave(manager_id, make_request_data(employee_id, days_from_today=20, span_days=2))
    assert second.status == LeaveRequestStatus.PENDING.value


# --------------------------------------------------------------------
# Approval workflow - the part that actually marks attendance
# --------------------------------------------------------------------

def test_approve_leave_request_marks_every_day_leave_on_the_attendance_roster(
    leave_service, attendance_service, manager_id, employee_id
):
    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id, days_from_today=5, span_days=3))

    approved = leave_service.approve_leave_request(manager_id, leave_request.id, "Approved, enjoy")
    assert approved.status == LeaveRequestStatus.APPROVED.value
    assert approved.decided_by_id == manager_id
    assert approved.decided_at is not None
    assert approved.decision_reason == "Approved, enjoy"

    records = attendance_service.list_for_employee(manager_id, employee_id)
    marked_dates = {r.attendance_date for r in records if r.status == AttendanceStatus.LEAVE.value}
    expected_dates = {leave_request.date_from + timedelta(days=i) for i in range(3)}
    assert marked_dates == expected_dates


def test_approving_overrides_an_existing_attendance_record_rather_than_erroring(
    leave_service, attendance_service, manager_id, employee_id
):
    """A day already (incorrectly) marked ABSENT before the leave was
    formally approved must end up LEAVE, not block the approval - and the
    override must be visible in the audit trail (attendance_corrected),
    not a silent overwrite."""
    from app.schemas.attendance import AttendanceMark

    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id, days_from_today=5, span_days=1))
    attendance_service.mark_attendance(
        manager_id,
        AttendanceMark(employee_id=employee_id, attendance_date=leave_request.date_from, status=AttendanceStatus.ABSENT),
    )

    leave_service.approve_leave_request(manager_id, leave_request.id)

    record = attendance_service.list_for_employee(manager_id, employee_id)[0]
    assert record.status == AttendanceStatus.LEAVE.value
    assert record.corrected_by_id == manager_id


def test_shift_supervisor_cannot_approve_leave(leave_service, shift_supervisor_id, employee_id):
    leave_request = leave_service.request_leave(shift_supervisor_id, make_request_data(employee_id))
    with pytest.raises(PermissionDeniedError):
        leave_service.approve_leave_request(shift_supervisor_id, leave_request.id)


def test_cannot_approve_an_already_decided_request(leave_service, manager_id, employee_id):
    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id))
    leave_service.approve_leave_request(manager_id, leave_request.id)
    with pytest.raises(ConflictError):
        leave_service.approve_leave_request(manager_id, leave_request.id)


def test_approve_without_an_attached_attendance_service_is_refused(db_session, auth_service, manager_id, employee_id):
    audit_repo = AuditLogRepository(db_session)
    bare_service = LeaveService(
        LeaveRequestRepository(db_session), EmployeeRepository(db_session), audit_repo, auth_service,
    )
    leave_request = bare_service.request_leave(manager_id, make_request_data(employee_id))
    with pytest.raises(ConflictError):
        bare_service.approve_leave_request(manager_id, leave_request.id)
    # Refused before any state changed - still PENDING, not silently
    # left half-applied.
    assert bare_service._get_or_raise(leave_request.id).status == LeaveRequestStatus.PENDING.value


# --------------------------------------------------------------------
# Rejection and cancellation
# --------------------------------------------------------------------

def test_reject_leave_request_requires_a_reason(leave_service, manager_id, employee_id):
    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id))
    with pytest.raises(ValueError):
        leave_service.reject_leave_request(manager_id, leave_request.id, "")


def test_reject_leave_request_does_not_touch_attendance(leave_service, attendance_service, manager_id, employee_id):
    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id))
    rejected = leave_service.reject_leave_request(manager_id, leave_request.id, "No cover available")
    assert rejected.status == LeaveRequestStatus.REJECTED.value
    assert rejected.decision_reason == "No cover available"
    assert attendance_service.list_for_employee(manager_id, employee_id) == []


def test_cancel_leave_request_requires_a_reason(leave_service, manager_id, employee_id):
    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id))
    with pytest.raises(ValueError):
        leave_service.cancel_leave_request(manager_id, leave_request.id, "")


def test_cancel_pending_leave_request(leave_service, manager_id, employee_id):
    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id))
    cancelled = leave_service.cancel_leave_request(manager_id, leave_request.id, "Employee withdrew the request")
    assert cancelled.status == LeaveRequestStatus.CANCELLED.value


def test_cannot_cancel_an_already_approved_leave_request(leave_service, manager_id, employee_id):
    leave_request = leave_service.request_leave(manager_id, make_request_data(employee_id))
    leave_service.approve_leave_request(manager_id, leave_request.id)
    with pytest.raises(ConflictError):
        leave_service.cancel_leave_request(manager_id, leave_request.id, "Changed my mind")


# --------------------------------------------------------------------
# Listing / view permission
# --------------------------------------------------------------------

def test_accountant_can_view_but_not_manage(db_session, auth_service, attendance_service, employee_id):
    seed_initial_data()
    accountant_id = make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id
    audit_repo = AuditLogRepository(db_session)
    leave_service = LeaveService(
        LeaveRequestRepository(db_session), EmployeeRepository(db_session),
        audit_repo, auth_service, attendance_service=attendance_service,
    )
    assert leave_service.list_leave_requests(accountant_id) == []
    with pytest.raises(PermissionDeniedError):
        leave_service.request_leave(accountant_id, make_request_data(employee_id))
