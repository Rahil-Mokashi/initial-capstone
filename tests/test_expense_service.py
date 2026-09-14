from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import ExpenseStatus, PaymentMethod, ShiftStatus, TankTransactionType, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.role import Role
from app.models.shift import Shift
from app.models.tank_transaction import TankTransaction
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.expense import ExpenseCategoryCreate, ExpenseCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.expense_service import ExpenseService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_expense.db")
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
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


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
def open_shift_id(db_session, admin_id):
    shift = Shift(shift_date=date.today(), shift_label="Morning", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift)
    db_session.commit()
    return shift.id


@pytest.fixture()
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def expense_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ExpenseService(
        ExpenseRepository(db_session), ExpenseCategoryRepository(db_session),
        EmployeeRepository(db_session), ShiftRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def category_id(expense_service, admin_id):
    return expense_service.create_category(admin_id, ExpenseCategoryCreate(name="Electricity")).id


@pytest.fixture()
def fuel_id(db_session):
    fuel = Fuel(fuel_type="Diesel", rate_per_liter=Decimal("90.00"))
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


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
    tank = tank_service.create_tank(
        admin_id, TankCreate(code="T-DIESEL", fuel_id=fuel_id, capacity=Decimal("10000"), opening_stock=Decimal("1000"))
    )
    return tank.id


@pytest.fixture()
def expense_service_with_tank(db_session, auth_service, tank_service):
    audit_repo = AuditLogRepository(db_session)
    return ExpenseService(
        ExpenseRepository(db_session), ExpenseCategoryRepository(db_session),
        EmployeeRepository(db_session), ShiftRepository(db_session), audit_repo, auth_service,
        tank_service=tank_service,
    )


def make_expense_data(**overrides):
    defaults = dict(amount=Decimal("500"), payment_method=PaymentMethod.CASH)
    defaults.update(overrides)
    return ExpenseCreate(**defaults)


# --------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------

def test_create_category(expense_service, admin_id):
    category = expense_service.create_category(admin_id, ExpenseCategoryCreate(name="Maintenance"))
    assert category.status == "active"


def test_duplicate_category_name_raises_conflict(expense_service, admin_id):
    expense_service.create_category(admin_id, ExpenseCategoryCreate(name="Maintenance"))
    with pytest.raises(ConflictError):
        expense_service.create_category(admin_id, ExpenseCategoryCreate(name="Maintenance"))


def test_create_category_denied_without_permission(expense_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        expense_service.create_category(attendant_id, ExpenseCategoryCreate(name="Maintenance"))


# --------------------------------------------------------------------
# Expenses
# --------------------------------------------------------------------

def test_create_expense(expense_service, admin_id, category_id, employee_id):
    expense = expense_service.create_expense(admin_id, make_expense_data(category_id=category_id, employee_id=employee_id))
    assert expense.status == ExpenseStatus.PENDING.value
    assert expense.amount == Decimal("500")


def test_create_expense_with_shift(expense_service, admin_id, category_id, employee_id, open_shift_id):
    expense = expense_service.create_expense(
        admin_id, make_expense_data(category_id=category_id, employee_id=employee_id, shift_id=open_shift_id)
    )
    assert expense.shift_id == open_shift_id


def test_expense_cannot_be_paid_on_credit(category_id, employee_id):
    with pytest.raises(ValueError):
        make_expense_data(category_id=category_id, employee_id=employee_id, payment_method=PaymentMethod.CREDIT)


def test_expense_rejects_inactive_category(expense_service, admin_id, category_id, employee_id, db_session):
    from app.models.expense import ExpenseCategory

    category = db_session.query(ExpenseCategory).filter_by(id=category_id).first()
    category.status = "inactive"
    db_session.commit()

    with pytest.raises(ConflictError):
        expense_service.create_expense(admin_id, make_expense_data(category_id=category_id, employee_id=employee_id))


def test_create_expense_denied_without_permission(expense_service, attendant_id, category_id, employee_id):
    with pytest.raises(PermissionDeniedError):
        expense_service.create_expense(attendant_id, make_expense_data(category_id=category_id, employee_id=employee_id))


def test_accountant_can_record_expense(expense_service, accountant_id, category_id, employee_id):
    expense = expense_service.create_expense(accountant_id, make_expense_data(category_id=category_id, employee_id=employee_id))
    assert expense.status == ExpenseStatus.PENDING.value


# --------------------------------------------------------------------
# Approval workflow
# --------------------------------------------------------------------

def test_approve_expense(expense_service, admin_id, category_id, employee_id):
    expense = expense_service.create_expense(admin_id, make_expense_data(category_id=category_id, employee_id=employee_id))
    approved = expense_service.approve_expense(admin_id, expense.id, "Looks fine")
    assert approved.status == ExpenseStatus.APPROVED.value
    assert approved.approved_by_id == admin_id
    assert approved.approved_at is not None


def test_reject_expense_requires_reason(expense_service, admin_id, category_id, employee_id):
    expense = expense_service.create_expense(admin_id, make_expense_data(category_id=category_id, employee_id=employee_id))
    with pytest.raises(ValueError):
        expense_service.reject_expense(admin_id, expense.id, "")


def test_reject_expense(expense_service, admin_id, category_id, employee_id):
    expense = expense_service.create_expense(admin_id, make_expense_data(category_id=category_id, employee_id=employee_id))
    rejected = expense_service.reject_expense(admin_id, expense.id, "Missing receipt")
    assert rejected.status == ExpenseStatus.REJECTED.value
    assert rejected.approval_remarks == "Missing receipt"


def test_cannot_approve_an_already_approved_expense(expense_service, admin_id, category_id, employee_id):
    expense = expense_service.create_expense(admin_id, make_expense_data(category_id=category_id, employee_id=employee_id))
    expense_service.approve_expense(admin_id, expense.id)
    with pytest.raises(ConflictError):
        expense_service.approve_expense(admin_id, expense.id)


def test_accountant_cannot_approve_expense(expense_service, accountant_id, category_id, employee_id):
    expense = expense_service.create_expense(accountant_id, make_expense_data(category_id=category_id, employee_id=employee_id))
    with pytest.raises(PermissionDeniedError):
        expense_service.approve_expense(accountant_id, expense.id)


# --------------------------------------------------------------------
# Internal fuel consumption (a vehicle/generator filled from a tank,
# recorded as an expense) - docs/daily-report-spec.md section 6.
# --------------------------------------------------------------------

def test_expense_with_only_quantity_rejected_by_schema(category_id, employee_id, tank_id):
    with pytest.raises(ValueError):
        make_expense_data(category_id=category_id, employee_id=employee_id, quantity=Decimal("40"))


def test_expense_with_only_tank_id_rejected_by_schema(category_id, employee_id, tank_id):
    with pytest.raises(ValueError):
        make_expense_data(category_id=category_id, employee_id=employee_id, tank_id=tank_id)


def test_expense_with_zero_quantity_rejected_by_schema(category_id, employee_id, tank_id):
    with pytest.raises(ValueError):
        make_expense_data(category_id=category_id, employee_id=employee_id, tank_id=tank_id, quantity=Decimal("0"))


def test_expense_with_tank_and_quantity_posts_internal_consumption_transaction(
    expense_service_with_tank, admin_id, category_id, employee_id, tank_id, tank_service, db_session,
):
    expense = expense_service_with_tank.create_expense(
        admin_id,
        make_expense_data(
            category_id=category_id, employee_id=employee_id, tank_id=tank_id, quantity=Decimal("40"),
            description="Diesel Exp (MH12VVX5868) 40Lit",
        ),
    )

    assert expense.tank_id == tank_id
    assert expense.quantity == Decimal("40.000")

    tank = tank_service.get_tank(admin_id, tank_id)
    assert tank.current_stock == Decimal("960.000")  # 1000 opening - 40 consumed

    transactions = [
        t for t in db_session.query(TankTransaction).filter_by(tank_id=tank_id).all()
        if t.transaction_type == TankTransactionType.INTERNAL_CONSUMPTION.value
    ]
    assert len(transactions) == 1
    assert transactions[0].quantity == Decimal("-40.000")
    assert transactions[0].reference == f"expense:{expense.id}"


def test_expense_with_tank_id_but_no_tank_service_attached_raises(
    expense_service, admin_id, category_id, employee_id, tank_id,
):
    with pytest.raises(ConflictError):
        expense_service.create_expense(
            admin_id,
            make_expense_data(category_id=category_id, employee_id=employee_id, tank_id=tank_id, quantity=Decimal("40")),
        )


def test_expense_and_tank_movement_roll_back_together_on_failure(
    expense_service_with_tank, admin_id, category_id, employee_id, tank_id, db_session,
):
    """Regression test for the atomicity requirement (CLAUDE.md: "Never
    allow partial financial writes"): if the tank draw is impossible (not
    enough stock), the expense record must not be left behind either -
    an orphaned expense with no matching stock movement is exactly the
    silent-drift bug this feature exists to close."""
    with pytest.raises(ConflictError):
        expense_service_with_tank.create_expense(
            admin_id,
            make_expense_data(
                category_id=category_id, employee_id=employee_id, tank_id=tank_id, quantity=Decimal("5000"),
            ),
        )

    from app.models.expense import Expense

    assert db_session.query(Expense).count() == 0
    assert db_session.query(TankTransaction).filter_by(tank_id=tank_id).count() == 0
