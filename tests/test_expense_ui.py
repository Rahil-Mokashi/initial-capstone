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
from app.models.employee import Employee
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.expense import ExpenseCategoryCreate
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.expense_service import ExpenseService
from app.services.shift_service import ShiftService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_expense_ui.db")
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
def employee_id(db_session):
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add(employee)
    db_session.commit()
    return employee.id


@pytest.fixture()
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def employee_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return EmployeeService(EmployeeRepository(db_session), None, UserRepository(db_session), None, audit_repo, auth_service)


@pytest.fixture()
def shift_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ShiftService(
        ShiftRepository(db_session), NozzleAssignmentRepository(db_session), EmployeeRepository(db_session),
        NozzleRepository(db_session), UserRepository(db_session), audit_repo, auth_service,
    )


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


def test_expense_window_gates_manage_buttons_for_view_only_role(
    qapp, expense_service, employee_service, shift_service, auth_service, accountant_id
):
    from app.ui.expense_window import ExpenseWindow

    window = ExpenseWindow(expense_service, employee_service, shift_service, auth_service, accountant_id)
    assert window.expenses_tab.add_button.isHidden() is False
    assert window.expenses_tab.approve_button.isHidden() is True
    assert window.categories_tab.add_button.isHidden() is False


def test_expense_form_records_expense(qapp, expense_service, employee_service, shift_service, admin_id, category_id, employee_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.expense_window import ExpenseFormDialog

    dialog = ExpenseFormDialog(expense_service, employee_service, shift_service, admin_id)
    dialog.amount_input.setValue(750)
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(expense_service.list_expenses(admin_id)) == 1


def test_category_form_creates_category(qapp, expense_service, admin_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.expense_window import ExpenseCategoryFormDialog

    dialog = ExpenseCategoryFormDialog(expense_service, admin_id)
    dialog.name_input.setText("Cleaning")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(expense_service.list_categories(admin_id)) == 1
