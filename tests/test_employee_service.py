from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import EmployeeStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_employee.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def admin_id(db_session):
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def attendant_id(db_session):
    role = db_session.query(Role).filter_by(name=UserRole.ATTENDANT.value).first()
    user = User(
        username="attendant1",
        email="attendant1@example.com",
        password_hash=hash_password("Attendant@123"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user.id


@pytest.fixture()
def employee_service(db_session):
    user_repo = UserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    session_repo = UserSessionRepository(db_session)
    auth_service = AuthService(user_repo, audit_repo, session_repo)

    employee_repo = EmployeeRepository(db_session)
    document_repo = EmployeeDocumentRepository(db_session)
    role_repo = RoleRepository(db_session)

    return EmployeeService(employee_repo, document_repo, user_repo, role_repo, audit_repo, auth_service)


def make_employee_data(**overrides) -> EmployeeCreate:
    defaults = dict(
        first_name="Ravi",
        last_name="Kumar",
        contact_number="+91 9876543210",
        joining_date=date(2026, 1, 1),
        designation="Attendant",
        department="Operations",
    )
    defaults.update(overrides)
    return EmployeeCreate(**defaults)


def test_create_employee_generates_sequential_code(employee_service, admin_id):
    e1 = employee_service.create_employee(admin_id, make_employee_data())
    e2 = employee_service.create_employee(admin_id, make_employee_data(first_name="Sita"))
    assert e1.employee_code == "EMP-0001"
    assert e2.employee_code == "EMP-0002"


def test_create_employee_records_audit_log(employee_service, admin_id, db_session):
    employee_service.create_employee(admin_id, make_employee_data())
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "employee_created" in events


def test_attendant_cannot_create_employee(employee_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        employee_service.create_employee(attendant_id, make_employee_data())


def test_invalid_contact_number_rejected_by_schema():
    with pytest.raises(ValidationError):
        make_employee_data(contact_number="not-a-phone!!")


def test_blank_name_rejected_by_schema():
    with pytest.raises(ValidationError):
        make_employee_data(first_name="   ")


def test_duplicate_user_link_raises_conflict(employee_service, admin_id, attendant_id):
    employee_service.create_employee(admin_id, make_employee_data(user_id=attendant_id))
    with pytest.raises(ConflictError):
        employee_service.create_employee(admin_id, make_employee_data(first_name="Other", user_id=attendant_id))


def test_unknown_role_id_raises_not_found(employee_service, admin_id):
    with pytest.raises(NotFoundError):
        employee_service.create_employee(admin_id, make_employee_data(role_id="does-not-exist"))


def test_update_employee_changes_fields_and_audits(employee_service, admin_id, db_session):
    employee = employee_service.create_employee(admin_id, make_employee_data())
    updated = employee_service.update_employee(
        admin_id, employee.id, EmployeeUpdate(designation="Senior Attendant")
    )
    assert updated.designation == "Senior Attendant"

    events = [log for log in db_session.query(AuditLog).all() if log.event_type == "employee_updated"]
    assert len(events) == 1


def test_change_status_to_on_leave(employee_service, admin_id):
    employee = employee_service.create_employee(admin_id, make_employee_data())
    updated = employee_service.change_status(admin_id, employee.id, EmployeeStatus.ON_LEAVE, "Medical leave")
    assert updated.status == EmployeeStatus.ON_LEAVE.value


def test_record_exit_sets_status_and_exit_date(employee_service, admin_id):
    employee = employee_service.create_employee(admin_id, make_employee_data())
    exited = employee_service.record_exit(admin_id, employee.id, date(2026, 6, 1), "Resigned")
    assert exited.status == EmployeeStatus.TERMINATED.value
    assert exited.exit_date == date(2026, 6, 1)


def test_record_exit_before_joining_date_rejected(employee_service, admin_id):
    employee = employee_service.create_employee(admin_id, make_employee_data())
    with pytest.raises(ValueError):
        employee_service.record_exit(admin_id, employee.id, date(2025, 1, 1), "Bad date")


def test_exit_never_hard_deletes_employee(employee_service, admin_id, db_session):
    employee = employee_service.create_employee(admin_id, make_employee_data())
    employee_service.record_exit(admin_id, employee.id, date(2026, 6, 1), "Resigned")

    row = db_session.query(Employee).filter_by(id=employee.id).first()
    assert row is not None
    assert row.is_deleted is False


def test_add_and_remove_document(employee_service, admin_id):
    employee = employee_service.create_employee(admin_id, make_employee_data())
    doc = employee_service.add_document(admin_id, employee.id, "ID Proof", "/docs/id.pdf")

    docs = employee_service._document_repo.list_for_employee(employee.id)
    assert len(docs) == 1

    employee_service.remove_document(admin_id, doc.id, "Wrong file uploaded")
    docs_after = employee_service._document_repo.list_for_employee(employee.id)
    assert len(docs_after) == 0


def test_get_employee_not_found_raises(employee_service, admin_id):
    with pytest.raises(NotFoundError):
        employee_service.get_employee(admin_id, "does-not-exist")


def test_list_employees_requires_view_permission(employee_service, admin_id, attendant_id):
    employee_service.create_employee(admin_id, make_employee_data())
    assert len(employee_service.list_employees(admin_id)) == 1
    with pytest.raises(PermissionDeniedError):
        employee_service.list_employees(attendant_id)
