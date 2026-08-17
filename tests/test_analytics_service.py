from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, ShiftStatus, UserRole
from app.core.dates import PeriodType
from app.core.exceptions import PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.role import Role
from app.models.shift import Shift
from app.models.supplier import Supplier
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
from app.repositories.purchase_order_repository import PurchaseOrderItemRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.expense import ExpenseCategoryCreate, ExpenseCreate
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.expense_service import ExpenseService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_analytics.db")
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
def analytics_service(db_session, auth_service):
    return AnalyticsService(
        SaleRepository(db_session), ExpenseRepository(db_session),
        PurchaseOrderItemRepository(db_session), FuelRepository(db_session), auth_service,
    )


def make_purchase(db_session, admin_id, fuel_id, quantity: Decimal, rate: Decimal, order_date: date):
    supplier = Supplier(name="Acme Fuels", phone="9999999999")
    db_session.add(supplier)
    db_session.commit()

    po = PurchaseOrder(po_number=f"PO-{order_date.isoformat()}-{rate}", supplier_id=supplier.id, created_by_id=admin_id, status="placed", order_date=order_date)
    db_session.add(po)
    db_session.commit()

    item = PurchaseOrderItem(purchase_order_id=po.id, fuel_id=fuel_id, quantity_ordered=quantity, rate_per_liter=rate)
    db_session.add(item)
    db_session.commit()


def make_sale(sale_service, admin_id, shift_id, nozzle_id, employee_id, quantity=Decimal("10")):
    return sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=quantity, payment_method=PaymentMethod.CASH),
    )


# --------------------------------------------------------------------
# Period performance
# --------------------------------------------------------------------

def test_period_performance_with_no_purchase_history_has_no_profit_figures(
    analytics_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id
):
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"))
    report = analytics_service.get_period_performance(admin_id, PeriodType.DAY, date.today())

    petrol = next(row for row in report.fuel_breakdown if row.fuel_type == "Petrol")
    assert petrol.revenue == Decimal("1000.00")
    assert petrol.estimated_gross_profit is None
    assert report.total_estimated_gross_profit is None


def test_period_performance_computes_weighted_average_cost_profit(
    db_session, analytics_service, sale_service, admin_id, fuel_id, open_shift_id, nozzle_id, employee_id
):
    make_purchase(db_session, admin_id, fuel_id, Decimal("1000"), Decimal("80.00"), date.today() - timedelta(days=5))
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"))

    report = analytics_service.get_period_performance(admin_id, PeriodType.DAY, date.today())

    petrol = next(row for row in report.fuel_breakdown if row.fuel_type == "Petrol")
    assert petrol.weighted_avg_cost == Decimal("80.00")
    assert petrol.estimated_cost_of_goods == Decimal("800.00")
    assert petrol.estimated_gross_profit == Decimal("200.00")  # 1000 revenue - 800 cost
    assert report.total_estimated_gross_profit == Decimal("200.00")


def test_weighted_average_cost_blends_multiple_purchases(
    db_session, analytics_service, sale_service, admin_id, fuel_id, open_shift_id, nozzle_id, employee_id
):
    make_purchase(db_session, admin_id, fuel_id, Decimal("1000"), Decimal("80.00"), date.today() - timedelta(days=10))
    make_purchase(db_session, admin_id, fuel_id, Decimal("1000"), Decimal("90.00"), date.today() - timedelta(days=5))
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"))

    report = analytics_service.get_period_performance(admin_id, PeriodType.DAY, date.today())

    petrol = next(row for row in report.fuel_breakdown if row.fuel_type == "Petrol")
    assert petrol.weighted_avg_cost == Decimal("85.00")  # (1000*80 + 1000*90) / 2000


def test_purchase_after_the_period_end_is_excluded_from_cost_basis(
    db_session, analytics_service, sale_service, admin_id, fuel_id, open_shift_id, nozzle_id, employee_id
):
    make_purchase(db_session, admin_id, fuel_id, Decimal("1000"), Decimal("80.00"), date.today() - timedelta(days=5))
    make_purchase(db_session, admin_id, fuel_id, Decimal("1000"), Decimal("200.00"), date.today() + timedelta(days=5))
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"))

    report = analytics_service.get_period_performance(admin_id, PeriodType.DAY, date.today())

    petrol = next(row for row in report.fuel_breakdown if row.fuel_type == "Petrol")
    assert petrol.weighted_avg_cost == Decimal("80.00")


def test_period_performance_deducts_approved_expenses_from_net_profit(
    db_session, analytics_service, sale_service, expense_service, admin_id, fuel_id, open_shift_id, nozzle_id, employee_id
):
    make_purchase(db_session, admin_id, fuel_id, Decimal("1000"), Decimal("80.00"), date.today() - timedelta(days=5))
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"))

    category = expense_service.create_category(admin_id, ExpenseCategoryCreate(name="Cleaning"))
    expense = expense_service.create_expense(
        admin_id, ExpenseCreate(category_id=category.id, amount=Decimal("50"), payment_method=PaymentMethod.CASH, employee_id=employee_id)
    )
    expense_service.approve_expense(admin_id, expense.id)

    report = analytics_service.get_period_performance(admin_id, PeriodType.DAY, date.today())

    assert report.total_expenses == Decimal("50.00")
    assert report.estimated_net_profit == Decimal("150.00")  # 200 gross profit - 50 expense


def test_pending_expense_is_not_deducted(
    db_session, analytics_service, sale_service, expense_service, admin_id, fuel_id, open_shift_id, nozzle_id, employee_id
):
    make_purchase(db_session, admin_id, fuel_id, Decimal("1000"), Decimal("80.00"), date.today() - timedelta(days=5))
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"))

    category = expense_service.create_category(admin_id, ExpenseCategoryCreate(name="Cleaning"))
    expense_service.create_expense(
        admin_id, ExpenseCreate(category_id=category.id, amount=Decimal("50"), payment_method=PaymentMethod.CASH, employee_id=employee_id)
    )

    report = analytics_service.get_period_performance(admin_id, PeriodType.DAY, date.today())
    assert report.total_expenses == Decimal("0")


def test_period_performance_denied_without_permission(analytics_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        analytics_service.get_period_performance(attendant_id, PeriodType.DAY, date.today())


def test_weekly_period_bounds_include_earlier_sale_in_the_same_week(
    db_session, analytics_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id
):
    make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, quantity=Decimal("10"))
    report = analytics_service.get_period_performance(admin_id, PeriodType.WEEK, date.today())

    petrol = next(row for row in report.fuel_breakdown if row.fuel_type == "Petrol")
    assert petrol.quantity_sold == Decimal("10.000")


# --------------------------------------------------------------------
# Sales forecast
# --------------------------------------------------------------------

def test_forecast_reports_insufficient_data_with_no_sales_history(analytics_service, admin_id, fuel_id):
    forecasts = analytics_service.get_sales_forecast(admin_id)
    petrol = next(f for f in forecasts if f.fuel_type == "Petrol")
    assert petrol.trend == "insufficient_data"
    assert petrol.predicted_next_week_quantity is None


def test_forecast_detects_an_increasing_trend(db_session, analytics_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id):
    # Build 4 weeks of steadily increasing sales by directly inserting
    # sales with dates in the past, since create_sale always stamps "now".
    from app.models.sale import Sale

    fuel = db_session.query(Fuel).first()
    quantities = [Decimal("100"), Decimal("120"), Decimal("140"), Decimal("160")]
    for weeks_ago, quantity in zip(range(len(quantities) - 1, -1, -1), quantities):
        sale_date = date.today() - timedelta(weeks=weeks_ago)
        sale = Sale(
            receipt_number=f"RCPT-TEST-{weeks_ago}",
            # Aware UTC: sale_at is a UTC instant (app/database/types.py).
            # A naive value here only ever "worked" while the columns were
            # naive too, and the session keeps the exact Python object
            # assigned (expire_on_commit=False), so it never gets corrected
            # on read.
            sale_at=datetime.combine(sale_date, time(12, 0), tzinfo=timezone.utc),
            shift_id=open_shift_id, nozzle_id=nozzle_id, fuel_id=fuel.id, employee_id=employee_id,
            quantity=quantity, rate_per_liter=Decimal("100.00"), amount=quantity * Decimal("100.00"),
            payment_method=PaymentMethod.CASH.value, status="completed", recorded_by_id=admin_id,
        )
        db_session.add(sale)
    db_session.commit()

    forecasts = analytics_service.get_sales_forecast(admin_id, weeks_of_history=4)
    petrol = next(f for f in forecasts if f.fuel_type == "Petrol")

    assert petrol.trend == "increasing"
    assert petrol.predicted_next_week_quantity > quantities[-1]
    assert petrol.predicted_next_week_revenue is not None


def test_forecast_denied_without_permission(analytics_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        analytics_service.get_sales_forecast(attendant_id)
