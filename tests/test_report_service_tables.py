from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, ShiftStatus, UserRole
from app.core.exceptions import PermissionDeniedError
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
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.credit import CreditAccountCreate
from app.schemas.customer import CustomerCreate
from app.schemas.expense import ExpenseCategoryCreate, ExpenseCreate
from app.schemas.sale import SaleCreate
from app.schemas.shift_reconciliation import ShiftReconciliationPerform
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.expense_service import ExpenseService
from app.services.reconciliation_service import ReconciliationService
from app.services.report_service import ReportService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_report_tables.db")
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
def expense_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ExpenseService(
        ExpenseRepository(db_session), ExpenseCategoryRepository(db_session),
        EmployeeRepository(db_session), ShiftRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def reconciliation_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ReconciliationService(
        ShiftReconciliationRepository(db_session), ShiftRepository(db_session),
        SaleRepository(db_session), ExpenseRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def report_service(db_session, auth_service):
    return ReportService(
        FuelRepository(db_session), TankRepository(db_session), NozzleRepository(db_session),
        FuelReconciliationRepository(db_session), auth_service,
        SaleRepository(db_session), PaymentRepository(db_session), ExpenseRepository(db_session),
        CreditAccountRepository(db_session), CustomerPaymentRepository(db_session),
        CustomerRepository(db_session), ShiftReconciliationRepository(db_session),
    )


def make_sale(sale_service, admin_id, shift_id, nozzle_id, employee_id, quantity=Decimal("10"), method=PaymentMethod.CASH, customer_id=None):
    return sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=quantity, payment_method=method, customer_id=customer_id),
    )


# --------------------------------------------------------------------
# Sales / payment reports
# --------------------------------------------------------------------

def test_sales_report_groups_by_fuel_type(report_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"))
    report = report_service.get_sales_report(admin_id)
    assert report.title == "Sales Report"
    assert any(row[0] == "Petrol" for row in report.rows)
    assert report.rows[-1][0] == "Total"


def test_attendant_can_view_sales_report(report_service, attendant_id):
    report = report_service.get_sales_report(attendant_id)
    assert report.title == "Sales Report"


def test_payment_summary_report_breaks_down_by_status(report_service, sale_service, credit_service, admin_id, open_shift_id, nozzle_id, employee_id):
    customer = sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports"))
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer.id, credit_limit=Decimal("5000")))
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("5"), method=PaymentMethod.CASH)
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("5"), method=PaymentMethod.CREDIT, customer_id=customer.id)

    report = report_service.get_payment_summary_report(admin_id)
    cash_row = next(row for row in report.rows if row[0] == "Cash")
    credit_row = next(row for row in report.rows if row[0] == "Credit")
    assert cash_row[2] == "500.00"  # success column
    assert credit_row[3] == "500.00"  # pending column


# --------------------------------------------------------------------
# Expense report
# --------------------------------------------------------------------

def test_expense_summary_report_breaks_down_by_status(report_service, expense_service, admin_id, employee_id):
    category = expense_service.create_category(admin_id, ExpenseCategoryCreate(name="Electricity"))
    expense = expense_service.create_expense(
        admin_id, ExpenseCreate(category_id=category.id, amount=Decimal("300"), payment_method=PaymentMethod.CASH, employee_id=employee_id)
    )
    expense_service.approve_expense(admin_id, expense.id)
    expense_service.create_expense(
        admin_id, ExpenseCreate(category_id=category.id, amount=Decimal("150"), payment_method=PaymentMethod.CASH, employee_id=employee_id)
    )

    report = report_service.get_expense_summary_report(admin_id)
    row = next(row for row in report.rows if row[0] == "Electricity")
    assert row[2] == "300.00"  # approved
    assert row[3] == "150.00"  # pending


# --------------------------------------------------------------------
# Credit reports
# --------------------------------------------------------------------

def test_credit_fuel_type_report(report_service, sale_service, credit_service, admin_id, open_shift_id, nozzle_id, employee_id):
    customer = sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports"))
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer.id, credit_limit=Decimal("5000")))
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"), method=PaymentMethod.CREDIT, customer_id=customer.id)

    report = report_service.get_credit_fuel_type_report(admin_id)
    petrol_row = next(row for row in report.rows if row[0] == "Petrol")
    assert petrol_row[2] == "1000.00"


def test_customer_outstanding_report(report_service, sale_service, credit_service, admin_id, open_shift_id, nozzle_id, employee_id):
    customer = sale_service.create_customer(admin_id, CustomerCreate(name="Ravi Transports"))
    credit_service.create_credit_account(admin_id, CreditAccountCreate(customer_id=customer.id, credit_limit=Decimal("5000")))
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"), method=PaymentMethod.CREDIT, customer_id=customer.id)

    report = report_service.get_customer_outstanding_report(admin_id)
    row = next(row for row in report.rows if row[0] == "Ravi Transports")
    assert row[2] == "1000.00"


# --------------------------------------------------------------------
# Reconciliation report
# --------------------------------------------------------------------

def test_reconciliation_report_lists_reconciliations(report_service, reconciliation_service, admin_id, open_shift_id):
    reconciliation_service.perform_shift_reconciliation(
        admin_id,
        ShiftReconciliationPerform(shift_id=open_shift_id, declared_cash=Decimal("0"), declared_upi=Decimal("0"), declared_card=Decimal("0")),
    )
    report = report_service.get_reconciliation_report(admin_id)
    assert len(report.rows) == 1
    assert report.rows[0][4] == "Normal"


# --------------------------------------------------------------------
# Permission gating
# --------------------------------------------------------------------

def test_expense_report_denied_for_attendant(report_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        report_service.get_expense_summary_report(attendant_id)


def test_credit_report_denied_for_attendant(report_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        report_service.get_credit_fuel_type_report(attendant_id)


def test_reconciliation_report_denied_for_attendant(report_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        report_service.get_reconciliation_report(attendant_id)
