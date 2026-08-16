from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, ShiftStatus, UserRole
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
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.purchase_order_repository import PurchaseOrderItemRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_analytics_ui.db")
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
def analytics_service(db_session, auth_service):
    return AnalyticsService(
        SaleRepository(db_session), ExpenseRepository(db_session),
        PurchaseOrderItemRepository(db_session), FuelRepository(db_session), auth_service,
    )


def test_performance_tab_shows_todays_sale(qapp, analytics_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    from app.ui.analytics_window import PerformanceTab

    sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("10"), payment_method=PaymentMethod.CASH),
    )
    tab = PerformanceTab(analytics_service, admin_id)
    assert tab.table.rowCount() > 0
    assert tab.table.item(0, 0).text() == "Petrol"


def test_forecast_tab_shows_insufficient_data_message(qapp, analytics_service, admin_id, fuel_id):
    from app.ui.analytics_window import ForecastTab

    tab = ForecastTab(analytics_service, admin_id)
    assert "Not enough" in tab.explanations_label.text()


def test_analytics_window_has_both_tabs(qapp, analytics_service, admin_id):
    from app.ui.analytics_window import AnalyticsWindow

    window = AnalyticsWindow(analytics_service, admin_id)
    assert window.performance_tab is not None
    assert window.forecast_tab is not None
