from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.exceptions import PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.dispenser_repository import DispenserRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.nozzle import DispenserCreate, NozzleCreate
from app.schemas.tank import ReconciliationPerform, TankCreate
from app.services.auth_service import AuthService
from app.services.nozzle_service import NozzleService
from app.services.report_service import ReportService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_report.db")
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
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def fuel_repo(db_session):
    return FuelRepository(db_session)


@pytest.fixture()
def tank_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return TankService(
        TankRepository(db_session),
        TankReadingRepository(db_session),
        TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session),
        FuelRepository(db_session),
        EmployeeRepository(db_session),
        audit_repo,
        auth_service,
    )


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
        TankRepository(db_session),
    )


@pytest.fixture()
def report_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return ReportService(
        FuelRepository(db_session),
        TankRepository(db_session),
        NozzleRepository(db_session),
        FuelReconciliationRepository(db_session),
        auth_service,
    )


def test_seeded_fuel_types_appear_with_zero_data(report_service, admin_id):
    summaries = report_service.get_fuel_type_summary(admin_id)
    fuel_types = {s.fuel_type for s in summaries}
    assert fuel_types == {"Petrol", "Diesel", "Power"}
    for summary in summaries:
        assert summary.tank_count == 0
        assert summary.nozzle_count == 0


def test_summary_aggregates_tanks_and_nozzles_per_fuel_type(report_service, tank_service, nozzle_service, fuel_repo, admin_id):
    petrol = next(f for f in fuel_repo.list_active() if f.fuel_type == "Petrol")

    tank_service.create_tank(admin_id, TankCreate(code="T1", fuel_id=petrol.id, capacity=10000.0, opening_stock=6000.0))
    tank_service.create_tank(admin_id, TankCreate(code="T2", fuel_id=petrol.id, capacity=8000.0, opening_stock=4000.0))

    dispenser = nozzle_service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    nozzle_service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=petrol.id))

    summaries = report_service.get_fuel_type_summary(admin_id)
    petrol_summary = next(s for s in summaries if s.fuel_type == "Petrol")

    assert petrol_summary.tank_count == 2
    assert petrol_summary.total_capacity == 18000.0
    assert petrol_summary.total_current_stock == 10000.0
    assert petrol_summary.nozzle_count == 1
    assert petrol_summary.active_nozzle_count == 1


def test_summary_includes_latest_reconciliation_variance(report_service, tank_service, fuel_repo, admin_id):
    diesel = next(f for f in fuel_repo.list_active() if f.fuel_type == "Diesel")
    tank = tank_service.create_tank(admin_id, TankCreate(code="T1", fuel_id=diesel.id, capacity=10000.0, opening_stock=1000.0))
    tank_service.perform_reconciliation(admin_id, tank.id, ReconciliationPerform(reconciliation_date=date.today(), physical_stock=800.0))

    summaries = report_service.get_fuel_type_summary(admin_id)
    diesel_summary = next(s for s in summaries if s.fuel_type == "Diesel")

    assert diesel_summary.latest_variance_classification == "approval_required"
    assert diesel_summary.latest_variance_percent is not None


def test_attendant_cannot_view_reports(report_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        report_service.get_fuel_type_summary(attendant_id)
