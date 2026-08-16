from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, ShiftStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.credit import CreditAccountCreate, CustomerPaymentCreate
from app.schemas.customer import CustomerCreate
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_credit.db")
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
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def tank_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
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
def credit_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return CreditService(
        CreditAccountRepository(db_session), CustomerPaymentRepository(db_session),
        CustomerRepository(db_session), SaleRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def sale_service(db_session, tank_service, credit_service, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return SaleService(
        SaleRepository(db_session), ShiftRepository(db_session), NozzleRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), CustomerRepository(db_session),
        TankRepository(db_session), tank_service, audit_repo, auth_service, PaymentRepository(db_session),
        credit_service,
    )


@pytest.fixture()
def customer_id(sale_service, admin_id):
    return sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports")).id


def make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("10")):
    return sale_service.create_sale(
        admin_id,
        SaleCreate(
            shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id,
            quantity=quantity, payment_method=PaymentMethod.CREDIT, customer_id=customer_id,
        ),
    )


# --------------------------------------------------------------------
# Credit accounts
# --------------------------------------------------------------------

def test_create_credit_account(credit_service, admin_id, customer_id):
    account = credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))
    assert account.credit_limit == Decimal("5000")
    assert account.payment_due_days == 30


def test_cannot_open_two_accounts_for_the_same_customer(credit_service, admin_id, customer_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))
    with pytest.raises(ConflictError):
        credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("2000")))


def test_create_credit_account_denied_without_permission(credit_service, attendant_id, customer_id):
    with pytest.raises(PermissionDeniedError):
        credit_service.create_credit_account(attendant_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))


def test_set_credit_limit_requires_reason(credit_service, admin_id, customer_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))
    with pytest.raises(ValueError):
        credit_service.set_credit_limit(admin_id, customer_id, Decimal("8000"), "")


def test_set_credit_limit(credit_service, admin_id, customer_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))
    updated = credit_service.set_credit_limit(admin_id, customer_id, Decimal("8000"), "Customer requested a higher limit")
    assert updated.credit_limit == Decimal("8000")


# --------------------------------------------------------------------
# Outstanding balance / credit-limit enforcement
# --------------------------------------------------------------------

def test_outstanding_balance_tracks_credit_sales(credit_service, sale_service, admin_id, customer_id, open_shift_id, nozzle_id, employee_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))
    make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("10"))
    assert credit_service.get_outstanding_balance(admin_id, customer_id) == Decimal("1000.00")


def test_recording_a_payment_reduces_outstanding_balance(credit_service, sale_service, admin_id, customer_id, open_shift_id, nozzle_id, employee_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))
    make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("10"))
    credit_service.record_customer_payment(
        admin_id, CustomerPaymentCreate(customer_id=customer_id, amount=Decimal("400"), payment_method=PaymentMethod.CASH)
    )
    assert credit_service.get_outstanding_balance(admin_id, customer_id) == Decimal("600.00")


def test_cannot_record_payment_without_credit_account(credit_service, admin_id, customer_id):
    with pytest.raises(NotFoundError):
        credit_service.record_customer_payment(
            admin_id, CustomerPaymentCreate(customer_id=customer_id, amount=Decimal("100"), payment_method=PaymentMethod.CASH)
        )


def test_sale_within_limit_succeeds(sale_service, credit_service, admin_id, customer_id, open_shift_id, nozzle_id, employee_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("2000")))
    sale = make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("10"))
    assert sale.amount == Decimal("1000.00")


def test_sale_exceeding_limit_is_blocked(sale_service, credit_service, admin_id, customer_id, open_shift_id, nozzle_id, employee_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("500")))
    with pytest.raises(ConflictError):
        make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("10"))


def test_a_payment_frees_up_credit_for_a_later_sale(sale_service, credit_service, admin_id, customer_id, open_shift_id, nozzle_id, employee_id, db_session):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("1000")))
    make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("10"))

    with pytest.raises(ConflictError):
        make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("5"))

    credit_service.record_customer_payment(
        admin_id, CustomerPaymentCreate(customer_id=customer_id, amount=Decimal("1000"), payment_method=PaymentMethod.CASH)
    )
    sale = make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("5"))
    assert sale.amount == Decimal("500.00")


# --------------------------------------------------------------------
# Statement / overdue
# --------------------------------------------------------------------

def test_customer_statement_running_balance(credit_service, sale_service, admin_id, customer_id, open_shift_id, nozzle_id, employee_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))
    make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("10"))
    credit_service.record_customer_payment(
        admin_id, CustomerPaymentCreate(customer_id=customer_id, amount=Decimal("300"), payment_method=PaymentMethod.CASH)
    )

    entries = credit_service.get_customer_statement(admin_id, customer_id)
    assert len(entries) == 2
    assert entries[-1].running_balance == Decimal("700.00")


def test_account_with_no_activity_is_not_overdue(credit_service, admin_id, customer_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000")))
    assert credit_service.is_overdue(admin_id, customer_id) is False


def test_fully_paid_account_is_not_overdue(credit_service, sale_service, admin_id, customer_id, open_shift_id, nozzle_id, employee_id):
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer_id, credit_limit=Decimal("5000"), payment_due_days=1))
    make_credit_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, customer_id, quantity=Decimal("10"))
    credit_service.record_customer_payment(
        admin_id, CustomerPaymentCreate(customer_id=customer_id, amount=Decimal("1000"), payment_method=PaymentMethod.CASH)
    )
    assert credit_service.is_overdue(admin_id, customer_id) is False


def test_list_credit_accounts_denied_without_permission(credit_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        credit_service.list_credit_accounts(attendant_id)
