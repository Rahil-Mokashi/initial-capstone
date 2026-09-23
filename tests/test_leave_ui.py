from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.employee import Employee
from app.models.role import Role
from app.models.user import User
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.leave_request_repository import LeaveRequestRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.leave_request import LeaveRequestCreate
from app.services.attendance_service import AttendanceService
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.leave_service import LeaveService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_leave_ui.db")
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
def attendance_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return AttendanceService(
        AttendanceRepository(db_session), EmployeeRepository(db_session),
        ShiftRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def leave_service(db_session, auth_service, attendance_service):
    audit_repo = AuditLogRepository(db_session)
    return LeaveService(
        LeaveRequestRepository(db_session), EmployeeRepository(db_session),
        audit_repo, auth_service, attendance_service=attendance_service,
    )


def test_leave_window_gates_manage_and_approve_buttons_for_view_only_role(
    qapp, leave_service, employee_service, auth_service, accountant_id
):
    from app.ui.leave_window import LeaveWindow

    window = LeaveWindow(leave_service, employee_service, auth_service, accountant_id)
    assert window.request_button.isHidden() is True
    assert window.approve_button.isHidden() is True
    assert window.reject_button.isHidden() is True
    assert window.cancel_button.isHidden() is True


def test_leave_window_shows_manage_and_approve_buttons_for_admin(
    qapp, leave_service, employee_service, auth_service, admin_id
):
    from app.ui.leave_window import LeaveWindow

    window = LeaveWindow(leave_service, employee_service, auth_service, admin_id)
    assert window.request_button.isHidden() is False
    assert window.approve_button.isHidden() is False


def test_leave_window_lists_existing_requests(qapp, leave_service, employee_service, auth_service, admin_id, employee_id):
    leave_service.request_leave(
        admin_id,
        LeaveRequestCreate(
            employee_id=employee_id, date_from=date.today() + timedelta(days=5),
            date_to=date.today() + timedelta(days=6), reason="Family function",
        ),
    )

    from app.ui.leave_window import LeaveWindow

    window = LeaveWindow(leave_service, employee_service, auth_service, admin_id)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 0).text() == "Ravi Kumar"
    assert window.table.item(0, 4).text() == "Pending"


def test_leave_request_form_creates_a_request(qapp, leave_service, employee_service, admin_id, employee_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.leave_window import LeaveRequestFormDialog

    dialog = LeaveRequestFormDialog(leave_service, employee_service, admin_id)
    dialog.reason_input.setText("Medical appointment")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    requests = leave_service.list_leave_requests(admin_id)
    assert len(requests) == 1
    assert requests[0].reason == "Medical appointment"


def test_leave_request_form_shows_validation_error_with_no_employees(qapp, leave_service, employee_service, admin_id):
    from app.ui.leave_window import LeaveRequestFormDialog

    dialog = LeaveRequestFormDialog(leave_service, employee_service, admin_id)
    dialog._save()

    assert dialog.error_label.isHidden() is False
    assert "No employees" in dialog.error_label.text()


def test_approve_button_approves_the_selected_request_and_refreshes(
    qapp, leave_service, employee_service, auth_service, admin_id, employee_id, monkeypatch
):
    from PySide6.QtCore import Qt

    from app.ui.leave_window import LeaveWindow

    leave_service.request_leave(
        admin_id,
        LeaveRequestCreate(
            employee_id=employee_id, date_from=date.today() + timedelta(days=5),
            date_to=date.today() + timedelta(days=5), reason="Personal"),
    )

    window = LeaveWindow(leave_service, employee_service, auth_service, admin_id)
    window.table.selectRow(0)
    monkeypatch.setattr("app.ui.leave_window.QInputDialog.getText", lambda *a, **k: ("Approved", True))

    window._approve_selected()

    assert window.table.item(0, 4).text() == "Approved"
