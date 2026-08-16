"""End-to-end integration test (Phase 19: "Create integration tests for
key workflows") - a full pump-day lifecycle wired together the same way
AppController wires it in app/ui/main_window.py, exercising the real
services (not each in isolation) so a wiring/integration regression
across modules would fail here even if every unit test still passes:

open shift -> assign an attendant to a nozzle -> record a cash sale and
a credit sale -> record and approve an expense -> complete the nozzle
assignment -> close the shift -> reconcile cash/UPI/card for the shift
-> confirm the fuel-type-sectioned sales report and the customer's
outstanding balance both reflect exactly what happened.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, ReconciliationStatus, VarianceClassification
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
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
from app.schemas.shift import NozzleAssignmentComplete, NozzleAssignmentCreate, ShiftOpen
from app.schemas.shift_reconciliation import ShiftReconciliationPerform
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.expense_service import ExpenseService
from app.services.reconciliation_service import ReconciliationService
from app.services.report_service import ReportService
from app.services.sale_service import SaleService
from app.services.shift_service import ShiftService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_integration.db")
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
def services(db_session):
    """Wire every service the same way AppController does, sharing one
    audit_repo/auth_service, so this test exercises the app's real
    integration graph rather than hand-picked isolated pieces."""

    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))

    employee_repo = EmployeeRepository(db_session)
    nozzle_repo = NozzleRepository(db_session)
    assignment_repo = NozzleAssignmentRepository(db_session)
    shift_repo = ShiftRepository(db_session)
    fuel_repo = FuelRepository(db_session)
    tank_repo = TankRepository(db_session)
    sale_repo = SaleRepository(db_session)
    customer_repo = CustomerRepository(db_session)

    shift_service = ShiftService(shift_repo, assignment_repo, employee_repo, nozzle_repo, UserRepository(db_session), audit_repo, auth_service)
    tank_service = TankService(
        tank_repo, TankReadingRepository(db_session), TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session), fuel_repo, employee_repo, audit_repo, auth_service,
    )
    credit_service = CreditService(
        CreditAccountRepository(db_session), CustomerPaymentRepository(db_session),
        customer_repo, sale_repo, audit_repo, auth_service,
    )
    sale_service = SaleService(
        sale_repo, shift_repo, nozzle_repo, fuel_repo, employee_repo, customer_repo,
        tank_repo, tank_service, audit_repo, auth_service, PaymentRepository(db_session), credit_service,
    )
    expense_service = ExpenseService(
        ExpenseRepository(db_session), ExpenseCategoryRepository(db_session),
        employee_repo, shift_repo, audit_repo, auth_service,
    )
    reconciliation_service = ReconciliationService(
        ShiftReconciliationRepository(db_session), shift_repo, sale_repo,
        ExpenseRepository(db_session), audit_repo, auth_service,
    )
    report_service = ReportService(
        fuel_repo, tank_repo, nozzle_repo, FuelReconciliationRepository(db_session), auth_service,
        sale_repo, PaymentRepository(db_session), ExpenseRepository(db_session),
        CreditAccountRepository(db_session), CustomerPaymentRepository(db_session), customer_repo,
        ShiftReconciliationRepository(db_session),
    )

    return {
        "shift": shift_service, "tank": tank_service, "sale": sale_service,
        "expense": expense_service, "reconciliation": reconciliation_service,
        "report": report_service, "credit": credit_service,
    }


def test_full_shift_lifecycle(db_session, admin_id, employee_id, fuel_id, services):
    tank = services["tank"].create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=20000.0, opening_stock=10000.0))

    dispenser = Dispenser(code="D1", status="active")
    db_session.add(dispenser)
    db_session.commit()
    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id, tank_id=tank.id, status="active")
    db_session.add(nozzle)
    db_session.commit()

    # 1. Open the shift and assign the attendant to the nozzle.
    shift = services["shift"].open_shift(admin_id, ShiftOpen(shift_date=date.today(), shift_label="Morning"))
    assignment = services["shift"].assign_nozzle(
        admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle.id, opening_meter=Decimal("1000"))
    )

    # 2. A credit customer needs an account before they can be sold to on credit.
    customer = services["sale"].create_customer(admin_id, CustomerCreate(name="Ravi Transports"))
    services["credit"].create_credit_account(admin_id, CreditAccountCreate(customer_id=customer.id, credit_limit=Decimal("5000")))

    # 3. Record one cash sale and one credit sale during the shift.
    cash_sale = services["sale"].create_sale(
        admin_id, SaleCreate(shift_id=shift.id, nozzle_id=nozzle.id, employee_id=employee_id, quantity=Decimal("20"), payment_method=PaymentMethod.CASH)
    )
    credit_sale = services["sale"].create_sale(
        admin_id, SaleCreate(shift_id=shift.id, nozzle_id=nozzle.id, employee_id=employee_id, quantity=Decimal("5"), payment_method=PaymentMethod.CREDIT, customer_id=customer.id)
    )
    assert cash_sale.amount == Decimal("2000.00")
    assert credit_sale.amount == Decimal("500.00")

    # 4. An approved cash expense during the shift reduces the till.
    category = services["expense"].create_category(admin_id, ExpenseCategoryCreate(name="Cleaning"))
    expense = services["expense"].create_expense(
        admin_id, ExpenseCreate(category_id=category.id, amount=Decimal("100"), payment_method=PaymentMethod.CASH, employee_id=employee_id, shift_id=shift.id)
    )
    services["expense"].approve_expense(admin_id, expense.id)

    # 5. Close out the attendant's assignment and the shift itself.
    services["shift"].complete_nozzle_assignment(admin_id, assignment.id, NozzleAssignmentComplete(closing_meter=Decimal("1025")))
    closed_shift = services["shift"].close_shift(admin_id, shift.id)
    assert closed_shift.status == "closed"

    # 6. Reconcile: expected cash = 2000 (cash sale) - 100 (cash expense) = 1900.
    #    The attendant declares exactly that - no variance expected.
    reconciliation = services["reconciliation"].perform_shift_reconciliation(
        admin_id,
        ShiftReconciliationPerform(shift_id=shift.id, declared_cash=Decimal("1900"), declared_upi=Decimal("0"), declared_card=Decimal("0")),
    )
    assert reconciliation.expected_cash == Decimal("1900.00")
    assert reconciliation.cash_variance == Decimal("0")
    assert reconciliation.classification == VarianceClassification.NORMAL.value
    assert reconciliation.status == ReconciliationStatus.ACCEPTED.value

    # 7. The sales report and the customer's outstanding balance both
    #    reflect exactly what happened, computed independently from the
    #    same underlying data - not asserted against each other, against
    #    the actual expected numbers.
    sales_report = services["report"].get_sales_report(admin_id)
    petrol_row = next(row for row in sales_report.rows if row[0] == "Petrol")
    assert petrol_row[1] == "2"  # 2 sales
    assert petrol_row[3] == "2500.00"  # 2000 cash + 500 credit

    outstanding = services["credit"].get_outstanding_balance(admin_id, customer.id)
    assert outstanding == Decimal("500.00")

    tank_after = services["tank"].get_tank(admin_id, tank.id)
    assert tank_after.current_stock == Decimal("10000.000") - Decimal("25.000")  # 20L + 5L sold
