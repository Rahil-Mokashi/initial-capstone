from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, PurchaseOrderStatus, ShiftStatus, UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.purchase_order import PurchaseOrder
from app.models.role import Role
from app.models.shift import Shift
from app.models.supplier import Supplier
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.purchase_order_repository import PurchaseOrderRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.dashboard_service import DashboardService
from app.services.credit_service import CreditService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_dashboard.db")
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
def sale_service(db_session, tank_service, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return SaleService(
        SaleRepository(db_session), ShiftRepository(db_session), NozzleRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), CustomerRepository(db_session),
        TankRepository(db_session), tank_service, audit_repo, auth_service, PaymentRepository(db_session),
        CreditService(
            CreditAccountRepository(db_session), CustomerPaymentRepository(db_session),
            CustomerRepository(db_session), SaleRepository(db_session), audit_repo, auth_service,
        ),
    )


@pytest.fixture()
def dashboard_service(db_session, auth_service):
    return DashboardService(
        SaleRepository(db_session), ShiftRepository(db_session), TankRepository(db_session),
        PurchaseOrderRepository(db_session), auth_service,
    )


def test_admin_sees_every_section(dashboard_service, admin_id):
    summary = dashboard_service.get_summary(admin_id)
    assert summary.sales_today_count == 0
    assert summary.sales_today_amount == Decimal("0")
    assert summary.open_shifts_count == 0
    assert summary.low_stock_tanks_count == 0
    assert summary.pending_purchase_orders_count == 0


def test_attendant_only_sees_sales_section(dashboard_service, attendant_id):
    summary = dashboard_service.get_summary(attendant_id)
    assert summary.sales_today_count == 0
    assert summary.open_shifts_count is None
    assert summary.low_stock_tanks_count is None
    assert summary.pending_purchase_orders_count is None


def test_todays_sale_is_counted(dashboard_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("10"), payment_method=PaymentMethod.CASH),
    )
    summary = dashboard_service.get_summary(admin_id)
    assert summary.sales_today_count == 1
    assert summary.sales_today_amount == Decimal("1000.00")


def test_cancelled_sale_excluded_from_todays_total(dashboard_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    sale = sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("10"), payment_method=PaymentMethod.CASH),
    )
    sale_service.cancel_sale(admin_id, sale.id, reason="Wrong amount")
    summary = dashboard_service.get_summary(admin_id)
    assert summary.sales_today_count == 0
    assert summary.sales_today_amount == Decimal("0")


def test_open_shift_is_counted(dashboard_service, admin_id, open_shift_id):
    summary = dashboard_service.get_summary(admin_id)
    assert summary.open_shifts_count == 1


def test_low_stock_tank_is_flagged(dashboard_service, tank_service, admin_id, fuel_id):
    tank_service.create_tank(admin_id, TankCreate(code="LOW", fuel_id=fuel_id, capacity=10000.0, opening_stock=1000.0))
    summary = dashboard_service.get_summary(admin_id)
    assert summary.low_stock_tanks_count == 1


def test_pending_purchase_order_is_counted(dashboard_service, db_session, admin_id, fuel_id):
    supplier = Supplier(name="Acme Fuels", phone="9999999999")
    db_session.add(supplier)
    db_session.commit()

    po = PurchaseOrder(po_number="PO-000001", supplier_id=supplier.id, created_by_id=admin_id, status=PurchaseOrderStatus.PLACED.value)
    db_session.add(po)
    db_session.commit()

    summary = dashboard_service.get_summary(admin_id)
    assert summary.pending_purchase_orders_count == 1


def test_recent_daily_sales_returns_one_entry_per_day_oldest_first(dashboard_service, admin_id):
    series = dashboard_service.get_recent_daily_sales(admin_id, days=7)
    assert len(series) == 7
    assert series[-1][0] == date.today()
    assert [day for day, _amount in series] == sorted(day for day, _amount in series)
    assert all(amount == Decimal("0") for _day, amount in series)


def test_recent_daily_sales_attributes_todays_sale_to_today(dashboard_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("10"), payment_method=PaymentMethod.CASH),
    )
    series = dashboard_service.get_recent_daily_sales(admin_id, days=7)
    today_total = dict(series)[date.today()]
    assert today_total == Decimal("1000.00")


def test_recent_daily_sales_excludes_cancelled_sales(dashboard_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    sale = sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("10"), payment_method=PaymentMethod.CASH),
    )
    sale_service.cancel_sale(admin_id, sale.id, reason="Wrong amount")
    series = dashboard_service.get_recent_daily_sales(admin_id, days=7)
    assert dict(series)[date.today()] == Decimal("0")


def test_recent_daily_sales_empty_for_a_role_without_sale_view(dashboard_service, db_session):
    from app.core.constants import UserRole

    seed_initial_data()
    no_access_id = make_user(db_session, UserRole.ATTENDANT.value, "noaccess").id
    # Strip the attendant's SALE_VIEW grant to prove the gate is real, not
    # just "attendants happen to always have it".
    from app.models.role import Role

    role = db_session.query(Role).filter_by(name=UserRole.ATTENDANT.value).first()
    role.permissions = [p for p in role.permissions if p.name != "sale.view"]
    db_session.commit()

    series = dashboard_service.get_recent_daily_sales(no_access_id, days=7)
    assert series == []
