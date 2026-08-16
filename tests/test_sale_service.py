from datetime import date, timezone, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, SaleStatus, ShiftStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base, StatusEnum
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.customer import CustomerCreate
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_sale.db")
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
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


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
def fuel_id(db_session):
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=Decimal("100.00"))
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


@pytest.fixture()
def tank_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return TankService(
        TankRepository(db_session), TankReadingRepository(db_session), TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session), FuelRepository(db_session), EmployeeRepository(db_session),
        audit_repo, auth_service,
    )


@pytest.fixture()
def tank_id(tank_service, admin_id, fuel_id):
    tank = tank_service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=20000.0, opening_stock=10000.0))
    return tank.id


@pytest.fixture()
def nozzle_id(db_session, fuel_id, tank_id):
    dispenser = Dispenser(code="D1", status="active")
    db_session.add(dispenser)
    db_session.commit()
    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id, tank_id=tank_id, status="active")
    db_session.add(nozzle)
    db_session.commit()
    return nozzle.id


@pytest.fixture()
def open_shift_id(db_session, admin_id):
    shift = Shift(shift_date=date.today(), shift_label="Morning", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift)
    db_session.commit()
    return shift.id


@pytest.fixture()
def sale_service(db_session, tank_service):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return SaleService(
        SaleRepository(db_session), ShiftRepository(db_session), NozzleRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), CustomerRepository(db_session),
        TankRepository(db_session), tank_service, audit_repo, auth_service,
    )


def make_sale_data(**overrides):
    defaults = dict(quantity=Decimal("10"), payment_method=PaymentMethod.CASH)
    defaults.update(overrides)
    return SaleCreate(**defaults)


# --------------------------------------------------------------------
# Sales
# --------------------------------------------------------------------

def test_create_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    sale = sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("10"), payment_method=PaymentMethod.CASH),
    )
    assert sale.receipt_number == "RCPT-000001"
    assert sale.rate_per_liter == Decimal("100.00")
    assert sale.amount == Decimal("1000.00")
    assert sale.status == SaleStatus.COMPLETED.value
    assert sale.tank_transaction_id is not None


def test_sale_decrements_tank_stock(sale_service, tank_service, admin_id, open_shift_id, nozzle_id, employee_id, tank_id):
    sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("10"), payment_method=PaymentMethod.CASH),
    )
    tank = tank_service.get_tank(admin_id, tank_id)
    assert tank.current_stock == Decimal("9990.000")


def test_receipt_numbers_are_sequential(sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    first = sale_service.create_sale(admin_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id))
    second = sale_service.create_sale(admin_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id))
    assert first.receipt_number == "RCPT-000001"
    assert second.receipt_number == "RCPT-000002"


def test_sale_price_snapshot_survives_later_price_change(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, db_session, fuel_id):
    sale = sale_service.create_sale(admin_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id))
    assert sale.rate_per_liter == Decimal("100.00")

    fuel = db_session.query(Fuel).filter_by(id=fuel_id).first()
    fuel.rate_per_liter = Decimal("150.00")
    db_session.commit()

    refreshed_sale = sale_service.get_sale(admin_id, sale.id)
    assert refreshed_sale.rate_per_liter == Decimal("100.00")
    assert refreshed_sale.amount == Decimal("1000.00")


def test_sale_rejects_closed_shift(sale_service, admin_id, nozzle_id, employee_id, db_session):
    shift = Shift(shift_date=date.today(), shift_label="Evening", opened_by_id=admin_id, status=ShiftStatus.CLOSED.value)
    db_session.add(shift)
    db_session.commit()

    with pytest.raises(ConflictError):
        sale_service.create_sale(admin_id, make_sale_data(shift_id=shift.id, nozzle_id=nozzle_id, employee_id=employee_id))


def test_sale_rejects_inactive_nozzle(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, db_session):
    nozzle = db_session.query(Nozzle).filter_by(id=nozzle_id).first()
    nozzle.status = "inactive"
    db_session.commit()

    with pytest.raises(ConflictError):
        sale_service.create_sale(admin_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id))


def test_credit_sale_requires_customer(sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    with pytest.raises(ValueError):
        sale_service.create_sale(
            admin_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, payment_method=PaymentMethod.CREDIT)
        )


def test_credit_sale_with_customer(sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    customer = sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports"))
    sale = sale_service.create_sale(
        admin_id,
        make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, payment_method=PaymentMethod.CREDIT, customer_id=customer.id),
    )
    assert sale.customer_id == customer.id
    assert sale.payment_method == PaymentMethod.CREDIT.value


def test_sale_denied_without_permission(sale_service, accountant_id, open_shift_id, nozzle_id, employee_id):
    with pytest.raises(PermissionDeniedError):
        sale_service.create_sale(accountant_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id))


def test_attendant_can_record_a_sale(sale_service, attendant_id, open_shift_id, nozzle_id, employee_id):
    sale = sale_service.create_sale(attendant_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id))
    assert sale.status == SaleStatus.COMPLETED.value


# --------------------------------------------------------------------
# Cancellation
# --------------------------------------------------------------------

def test_cancel_sale_requires_reason(sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    sale = sale_service.create_sale(admin_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id))
    with pytest.raises(ValueError):
        sale_service.cancel_sale(admin_id, sale.id, "")


def test_cancel_sale_restores_tank_stock(sale_service, tank_service, admin_id, open_shift_id, nozzle_id, employee_id, tank_id):
    sale = sale_service.create_sale(admin_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("10")))
    before = tank_service.get_tank(admin_id, tank_id).current_stock

    cancelled = sale_service.cancel_sale(admin_id, sale.id, "Customer changed their mind before leaving")
    assert cancelled.status == SaleStatus.CANCELLED.value

    after = tank_service.get_tank(admin_id, tank_id).current_stock
    assert after == before + Decimal("10")


def test_cannot_cancel_an_already_cancelled_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    sale = sale_service.create_sale(admin_id, make_sale_data(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id))
    sale_service.cancel_sale(admin_id, sale.id, "First cancellation")
    with pytest.raises(ConflictError):
        sale_service.cancel_sale(admin_id, sale.id, "Second cancellation")


# --------------------------------------------------------------------
# Customers
# --------------------------------------------------------------------

def test_create_customer(sale_service, admin_id):
    customer = sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports"))
    assert customer.status == StatusEnum.ACTIVE.value


def test_duplicate_customer_name_raises_conflict(sale_service, admin_id):
    sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports"))
    with pytest.raises(ConflictError):
        sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports"))


def test_set_customer_status_requires_reason(sale_service, admin_id):
    customer = sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports"))
    with pytest.raises(ValueError):
        sale_service.set_customer_status(admin_id, customer.id, StatusEnum.INACTIVE, "")
