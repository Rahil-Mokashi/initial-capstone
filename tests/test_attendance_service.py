from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import AttendanceStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.attendance import AttendanceCorrection, AttendanceMark
from app.schemas.employee import EmployeeCreate
from app.services.attendance_service import AttendanceService
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_attendance.db")
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
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"),
        role=role,
        is_active=True,
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
def shift_supervisor_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.SHIFT_SUPERVISOR.value, "supervisor1").id


@pytest.fixture()
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


@pytest.fixture()
def employee_service(db_session):
    user_repo = UserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(user_repo, audit_repo, UserSessionRepository(db_session))
    return EmployeeService(
        EmployeeRepository(db_session),
        EmployeeDocumentRepository(db_session),
        user_repo,
        RoleRepository(db_session),
        audit_repo,
        auth_service,
    )


@pytest.fixture()
def attendance_service(db_session, employee_service):
    user_repo = UserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(user_repo, audit_repo, UserSessionRepository(db_session))
    return AttendanceService(AttendanceRepository(db_session), EmployeeRepository(db_session), audit_repo, auth_service)


@pytest.fixture()
def employee_id(employee_service, admin_id):
    employee = employee_service.create_employee(
        admin_id,
        EmployeeCreate(
            first_name="Ravi",
            last_name="Kumar",
            contact_number="+91 9876543210",
            joining_date=date(2026, 1, 1),
        ),
    )
    return employee.id


def test_mark_attendance_creates_record(attendance_service, admin_id, employee_id):
    record = attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.PRESENT),
    )
    assert record.status == AttendanceStatus.PRESENT.value
    assert record.employee_id == employee_id


def test_mark_attendance_records_audit_log(attendance_service, admin_id, employee_id, db_session):
    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.PRESENT),
    )
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "attendance_marked" in events


def test_duplicate_attendance_for_same_day_raises_conflict(attendance_service, admin_id, employee_id):
    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.PRESENT),
    )
    with pytest.raises(ConflictError):
        attendance_service.mark_attendance(
            admin_id,
            AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.ABSENT),
        )


def test_mark_attendance_unknown_employee_raises_not_found(attendance_service, admin_id):
    with pytest.raises(NotFoundError):
        attendance_service.mark_attendance(
            admin_id,
            AttendanceMark(employee_id="does-not-exist", attendance_date=date(2026, 2, 1), status=AttendanceStatus.PRESENT),
        )


def test_shift_supervisor_can_mark_attendance(attendance_service, shift_supervisor_id, employee_id):
    record = attendance_service.mark_attendance(
        shift_supervisor_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.PRESENT),
    )
    assert record.status == AttendanceStatus.PRESENT.value


def test_accountant_cannot_mark_attendance(attendance_service, accountant_id, employee_id):
    with pytest.raises(PermissionDeniedError):
        attendance_service.mark_attendance(
            accountant_id,
            AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.PRESENT),
        )


def test_accountant_can_view_attendance(attendance_service, admin_id, accountant_id, employee_id):
    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.PRESENT),
    )
    records = attendance_service.list_for_employee(accountant_id, employee_id)
    assert len(records) == 1


def test_check_out_before_check_in_rejected_by_schema():
    with pytest.raises(ValidationError):
        AttendanceMark(
            employee_id="e1",
            attendance_date=date(2026, 2, 1),
            status=AttendanceStatus.PRESENT,
            check_in_time=datetime(2026, 2, 1, 14, 0, tzinfo=timezone.utc),
            check_out_time=datetime(2026, 2, 1, 8, 0, tzinfo=timezone.utc),
        )


def test_negative_overtime_rejected_by_schema():
    with pytest.raises(ValidationError):
        AttendanceMark(employee_id="e1", attendance_date=date(2026, 2, 1), status=AttendanceStatus.PRESENT, overtime_minutes=-5)


def test_correct_attendance_requires_nonblank_reason(attendance_service, admin_id, employee_id):
    record = attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.ABSENT),
    )
    with pytest.raises(ValueError):
        attendance_service.correct_attendance(admin_id, record.id, AttendanceCorrection(status=AttendanceStatus.PRESENT), "")


def test_correct_attendance_updates_and_audits(attendance_service, admin_id, employee_id, db_session):
    record = attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 1), status=AttendanceStatus.ABSENT),
    )
    corrected = attendance_service.correct_attendance(
        admin_id,
        record.id,
        AttendanceCorrection(status=AttendanceStatus.PRESENT),
        "Employee was actually present, marked in error",
    )

    assert corrected.status == AttendanceStatus.PRESENT.value
    assert corrected.corrected_by_id == admin_id
    assert corrected.correction_reason == "Employee was actually present, marked in error"

    events = [log for log in db_session.query(AuditLog).all() if log.event_type == "attendance_corrected"]
    assert len(events) == 1
    assert "status=absent" in events[0].old_value
    assert "status=present" in events[0].new_value


def test_list_for_employee_filters_by_date_range(attendance_service, admin_id, employee_id):
    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 1, 15), status=AttendanceStatus.PRESENT),
    )
    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 2, 15), status=AttendanceStatus.PRESENT),
    )
    records = attendance_service.list_for_employee(admin_id, employee_id, date_from=date(2026, 2, 1))
    assert len(records) == 1
    assert records[0].attendance_date == date(2026, 2, 15)


def test_list_for_date_returns_all_employees_marked_that_day(attendance_service, employee_service, admin_id, employee_id):
    other_employee = employee_service.create_employee(
        admin_id,
        EmployeeCreate(first_name="Sita", last_name="Verma", contact_number="9123456780", joining_date=date(2026, 1, 1)),
    )
    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 3, 1), status=AttendanceStatus.PRESENT),
    )
    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=other_employee.id, attendance_date=date(2026, 3, 1), status=AttendanceStatus.ABSENT),
    )
    records = attendance_service.list_for_date(admin_id, date(2026, 3, 1))
    assert len(records) == 2
