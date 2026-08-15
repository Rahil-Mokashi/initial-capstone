from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import TankStatus, TankTransactionType, UserRole, VarianceClassification
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.role import Role
from app.models.tank_transaction import TankTransaction
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.tank import ReconciliationPerform, TankCreate, TankReadingCreate, TankTransactionCreate
from app.services.auth_service import AuthService
from app.services.tank_service import TankService, classify_variance


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_tank.db")
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
def fuel_id(db_session):
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=100.0)
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


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


def make_tank(tank_service, admin_id, fuel_id, **overrides):
    defaults = dict(code="T1", fuel_id=fuel_id, capacity=10000.0, opening_stock=5000.0)
    defaults.update(overrides)
    return tank_service.create_tank(admin_id, TankCreate(**defaults))


def test_create_tank(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    assert tank.code == "T1"
    assert tank.current_stock == 5000.0
    assert tank.status == TankStatus.ACTIVE.value


def test_create_tank_records_audit_log(tank_service, admin_id, fuel_id, db_session):
    make_tank(tank_service, admin_id, fuel_id)
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "tank_created" in events


def test_duplicate_tank_code_raises_conflict(tank_service, admin_id, fuel_id):
    make_tank(tank_service, admin_id, fuel_id)
    with pytest.raises(ConflictError):
        make_tank(tank_service, admin_id, fuel_id)


def test_create_tank_unknown_fuel_raises_not_found(tank_service, admin_id):
    with pytest.raises(NotFoundError):
        tank_service.create_tank(admin_id, TankCreate(code="T1", fuel_id="does-not-exist", capacity=10000.0))


def test_opening_stock_exceeding_capacity_rejected(tank_service, admin_id, fuel_id):
    with pytest.raises(ConflictError):
        make_tank(tank_service, admin_id, fuel_id, opening_stock=20000.0)


def test_negative_capacity_rejected_by_schema():
    with pytest.raises(ValidationError):
        TankCreate(code="T1", fuel_id="x", capacity=-1.0)


def test_attendant_cannot_create_tank(tank_service, attendant_id, fuel_id):
    with pytest.raises(PermissionDeniedError):
        make_tank(tank_service, attendant_id, fuel_id)


def test_record_receipt_increases_stock(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    tank_service.record_transaction(
        admin_id, tank.id, TankTransactionType.RECEIPT, TankTransactionCreate(quantity=2000.0)
    )
    updated = tank_service.get_tank(admin_id, tank.id)
    assert updated.current_stock == 7000.0


def test_record_issue_decreases_stock(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    tank_service.record_transaction(
        admin_id, tank.id, TankTransactionType.ISSUE, TankTransactionCreate(quantity=1000.0)
    )
    updated = tank_service.get_tank(admin_id, tank.id)
    assert updated.current_stock == 4000.0


def test_receipt_exceeding_capacity_rejected(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    with pytest.raises(ConflictError):
        tank_service.record_transaction(
            admin_id, tank.id, TankTransactionType.RECEIPT, TankTransactionCreate(quantity=6000.0)
        )


def test_issue_exceeding_current_stock_rejected(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    with pytest.raises(ConflictError):
        tank_service.record_transaction(
            admin_id, tank.id, TankTransactionType.ISSUE, TankTransactionCreate(quantity=6000.0)
        )


def test_adjustment_requires_reason(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    with pytest.raises(ValueError):
        tank_service.record_transaction(
            admin_id, tank.id, TankTransactionType.ADJUSTMENT, TankTransactionCreate(quantity=-50.0, remarks="")
        )


def test_negative_adjustment_reduces_stock(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    tank_service.record_transaction(
        admin_id, tank.id, TankTransactionType.ADJUSTMENT,
        TankTransactionCreate(quantity=-200.0, remarks="Correcting meter drift"),
    )
    updated = tank_service.get_tank(admin_id, tank.id)
    assert updated.current_stock == 4800.0


def test_record_reading(tank_service, admin_id, fuel_id, employee_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    reading = tank_service.record_reading(
        admin_id, tank.id, TankReadingCreate(employee_id=employee_id, physical_stock=4950.0)
    )
    assert reading.physical_stock == 4950.0
    # A reading is just an observation; it must not silently change the book stock.
    assert tank_service.get_tank(admin_id, tank.id).current_stock == 5000.0


@pytest.mark.parametrize(
    "variance_percent,expected",
    [
        (0.0, VarianceClassification.NORMAL),
        (0.4, VarianceClassification.NORMAL),
        (0.7, VarianceClassification.WARNING),
        (1.5, VarianceClassification.INVESTIGATION_REQUIRED),
        (5.0, VarianceClassification.APPROVAL_REQUIRED),
        (-5.0, VarianceClassification.APPROVAL_REQUIRED),
    ],
)
def test_classify_variance(variance_percent, expected):
    assert classify_variance(variance_percent) == expected


def test_perform_reconciliation_normal_case(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id, opening_stock=1000.0)
    tank_service.record_transaction(
        admin_id, tank.id, TankTransactionType.RECEIPT, TankTransactionCreate(quantity=500.0)
    )
    tank_service.record_transaction(
        admin_id, tank.id, TankTransactionType.ISSUE, TankTransactionCreate(quantity=200.0)
    )
    # expected = 1000 + 500 - 200 = 1300
    reconciliation = tank_service.perform_reconciliation(
        admin_id, tank.id, ReconciliationPerform(reconciliation_date=date.today(), physical_stock=1300.0)
    )
    assert reconciliation.expected_closing_stock == 1300.0
    assert reconciliation.variance == 0.0
    assert reconciliation.classification == VarianceClassification.NORMAL.value


def test_perform_reconciliation_large_variance_flagged_for_approval(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id, opening_stock=1000.0)
    reconciliation = tank_service.perform_reconciliation(
        admin_id, tank.id, ReconciliationPerform(reconciliation_date=date.today(), physical_stock=800.0)
    )
    assert reconciliation.classification == VarianceClassification.APPROVAL_REQUIRED.value


def test_reconciliation_resets_tank_stock_to_physical_and_audits(tank_service, admin_id, fuel_id, db_session):
    tank = make_tank(tank_service, admin_id, fuel_id, opening_stock=1000.0)
    tank_service.perform_reconciliation(
        admin_id, tank.id, ReconciliationPerform(reconciliation_date=date.today(), physical_stock=950.0)
    )
    updated = tank_service.get_tank(admin_id, tank.id)
    assert updated.current_stock == 950.0
    assert updated.opening_stock == 950.0

    events = [log for log in db_session.query(AuditLog).all() if log.event_type == "fuel_reconciliation_performed"]
    assert len(events) == 1


def test_second_reconciliation_uses_first_as_new_opening_stock(tank_service, admin_id, fuel_id):
    # All transactions are timestamped with the real clock, so both
    # reconciliations must fall on/after "today" for the second one's
    # date-bounded query to actually include the receipt recorded between them.
    tank = make_tank(tank_service, admin_id, fuel_id, opening_stock=1000.0)
    tank_service.perform_reconciliation(
        admin_id, tank.id, ReconciliationPerform(reconciliation_date=date.today(), physical_stock=950.0)
    )
    tank_service.record_transaction(
        admin_id, tank.id, TankTransactionType.RECEIPT, TankTransactionCreate(quantity=100.0)
    )
    second = tank_service.perform_reconciliation(
        admin_id, tank.id, ReconciliationPerform(reconciliation_date=date.today(), physical_stock=1050.0)
    )
    assert second.opening_stock == 950.0
    assert second.expected_closing_stock == 1050.0
    assert second.variance == 0.0


def test_set_tank_status_requires_reason(tank_service, admin_id, fuel_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    with pytest.raises(ValueError):
        tank_service.set_tank_status(admin_id, tank.id, TankStatus.MAINTENANCE, "")


def test_sum_for_tank_by_type_finds_a_transaction_recorded_just_now_when_queried_for_today(
    tank_service, admin_id, fuel_id, db_session
):
    """Regression test: sum_for_tank_by_type widens date_from/date_to (local
    calendar dates) to full-day boundaries before comparing against
    transaction_at (stored UTC-aware). A transaction recorded "now" must
    always be found when querying for "today" — this silently failed
    whenever local time ran ahead of UTC (e.g. IST, UTC+5:30) and the
    naive local-midnight boundary was compared directly against the
    UTC-stamped column, because the transaction's UTC timestamp is still
    technically "yesterday" from UTC's point of view."""
    tank = make_tank(tank_service, admin_id, fuel_id)
    transaction = TankTransaction(
        tank_id=tank.id,
        transaction_type=TankTransactionType.RECEIPT.value,
        quantity=Decimal("100.0"),
        recorded_by_id=admin_id,
        transaction_at=datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.commit()

    txn_repo = TankTransactionRepository(db_session)
    total = txn_repo.sum_for_tank_by_type(
        tank.id, TankTransactionType.RECEIPT.value, date_from=date.today(), date_to=date.today()
    )
    assert total == 100.0


def test_sum_for_tank_by_type_excludes_transactions_outside_the_requested_day(
    tank_service, admin_id, fuel_id, db_session
):
    tank = make_tank(tank_service, admin_id, fuel_id)
    yesterday_transaction = TankTransaction(
        tank_id=tank.id,
        transaction_type=TankTransactionType.RECEIPT.value,
        quantity=Decimal("50.0"),
        recorded_by_id=admin_id,
        transaction_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db_session.add(yesterday_transaction)
    db_session.commit()

    txn_repo = TankTransactionRepository(db_session)
    total = txn_repo.sum_for_tank_by_type(
        tank.id, TankTransactionType.RECEIPT.value, date_from=date.today(), date_to=date.today()
    )
    assert total == 0


def test_list_tanks_readings_transactions_reconciliations(tank_service, admin_id, fuel_id, employee_id):
    tank = make_tank(tank_service, admin_id, fuel_id)
    tank_service.record_reading(admin_id, tank.id, TankReadingCreate(employee_id=employee_id, physical_stock=4990.0))
    tank_service.record_transaction(
        admin_id, tank.id, TankTransactionType.RECEIPT, TankTransactionCreate(quantity=100.0)
    )
    tank_service.perform_reconciliation(
        admin_id, tank.id, ReconciliationPerform(reconciliation_date=date.today(), physical_stock=5100.0)
    )

    assert len(tank_service.list_tanks(admin_id)) == 1
    assert len(tank_service.list_readings(admin_id, tank.id)) == 1
    assert len(tank_service.list_transactions(admin_id, tank.id)) == 1
    assert len(tank_service.list_reconciliations(admin_id, tank.id)) == 1
