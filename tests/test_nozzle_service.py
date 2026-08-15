import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import NozzleStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base, StatusEnum
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.fuel import Fuel
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.dispenser_repository import DispenserRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.nozzle import DispenserCreate, NozzleCreate
from app.services.auth_service import AuthService
from app.services.nozzle_service import NozzleService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_nozzle.db")
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
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def fuel_id(db_session):
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=100.0, capacity=10000.0, current_stock=5000.0)
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


@pytest.fixture()
def nozzle_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return NozzleService(
        DispenserRepository(db_session),
        NozzleRepository(db_session),
        FuelRepository(db_session),
        NozzleAssignmentRepository(db_session),
        audit_repo,
        auth_service,
    )


def test_create_dispenser(nozzle_service, admin_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    assert dispenser.code == "D1"
    assert dispenser.status == "active"


def test_create_dispenser_records_audit_log(nozzle_service, admin_id, db_session):
    nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "dispenser_created" in events


def test_duplicate_dispenser_code_raises_conflict(nozzle_service, admin_id):
    nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    with pytest.raises(ConflictError):
        nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))


def test_attendant_cannot_create_dispenser(nozzle_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        nozzle_service.create_dispenser(attendant_id, DispenserCreate(code="D1"))


def test_blank_dispenser_code_rejected_by_schema():
    with pytest.raises(ValidationError):
        DispenserCreate(code="   ")


def test_create_nozzle(nozzle_service, admin_id, fuel_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    nozzle = nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))
    assert nozzle.code == "N1"
    assert nozzle.status == NozzleStatus.ACTIVE.value


def test_duplicate_nozzle_code_raises_conflict(nozzle_service, admin_id, fuel_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))
    with pytest.raises(ConflictError):
        nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))


def test_create_nozzle_unknown_dispenser_raises_not_found(nozzle_service, admin_id, fuel_id):
    with pytest.raises(NotFoundError):
        nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id="does-not-exist", fuel_id=fuel_id))


def test_create_nozzle_unknown_fuel_raises_not_found(nozzle_service, admin_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    with pytest.raises(NotFoundError):
        nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id="does-not-exist"))


def test_create_nozzle_on_inactive_dispenser_raises_conflict(nozzle_service, admin_id, fuel_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    nozzle_service.set_dispenser_status(admin_id, dispenser.id, StatusEnum.INACTIVE, "Under maintenance")
    with pytest.raises(ConflictError):
        nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))


def test_set_dispenser_status_requires_reason(nozzle_service, admin_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    with pytest.raises(ValueError):
        nozzle_service.set_dispenser_status(admin_id, dispenser.id, StatusEnum.INACTIVE, "")


def test_set_nozzle_status_requires_reason(nozzle_service, admin_id, fuel_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    nozzle = nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))
    with pytest.raises(ValueError):
        nozzle_service.set_nozzle_status(admin_id, nozzle.id, NozzleStatus.MAINTENANCE, "")


def test_set_nozzle_status_to_maintenance_and_audits(nozzle_service, admin_id, fuel_id, db_session):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    nozzle = nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))
    updated = nozzle_service.set_nozzle_status(admin_id, nozzle.id, NozzleStatus.MAINTENANCE, "Leak detected")
    assert updated.status == NozzleStatus.MAINTENANCE.value

    events = [log for log in db_session.query(AuditLog).all() if log.event_type == "nozzle_status_changed"]
    assert len(events) == 1
    assert events[0].description == "Leak detected"


def test_cannot_deactivate_nozzle_with_active_assignment(nozzle_service, admin_id, fuel_id, db_session):
    from datetime import date

    from app.models.employee import Employee
    from app.models.nozzle_assignment import NozzleAssignment

    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    nozzle = nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))

    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add(employee)
    db_session.commit()

    from app.models.shift import Shift

    shift = Shift(shift_date=date(2026, 1, 1), shift_label="Morning", opened_by_id=admin_id, status="open")
    db_session.add(shift)
    db_session.commit()

    assignment = NozzleAssignment(
        employee_id=employee.id, nozzle_id=nozzle.id, shift_id=shift.id,
        opening_meter=100.0, assigned_by_id=admin_id, status="active",
    )
    db_session.add(assignment)
    db_session.commit()

    with pytest.raises(ConflictError):
        nozzle_service.set_nozzle_status(admin_id, nozzle.id, NozzleStatus.INACTIVE, "Retiring nozzle")


def test_list_dispensers_and_nozzles(nozzle_service, admin_id, fuel_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))

    assert len(nozzle_service.list_dispensers(admin_id)) == 1
    assert len(nozzle_service.list_nozzles(admin_id)) == 1


def test_shift_supervisor_can_view_but_not_manage(nozzle_service, admin_id, shift_supervisor_id, fuel_id):
    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    assert len(nozzle_service.list_dispensers(shift_supervisor_id)) == 1
    with pytest.raises(PermissionDeniedError):
        nozzle_service.create_nozzle(shift_supervisor_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))
