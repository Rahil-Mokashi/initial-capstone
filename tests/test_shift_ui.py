from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.nozzle import Nozzle
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.employee import EmployeeCreate
from app.schemas.shift import ShiftOpen
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.shift_service import ShiftService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_shift_ui.db")
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
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"),
        role=role,
        is_active=True,
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
def employee_service(db_session):
    user_repo = UserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(user_repo, audit_repo, UserSessionRepository(db_session))
    return EmployeeService(
        EmployeeRepository(db_session),
        EmployeeDocumentRepository(db_session),
        user_repo,
        RoleRepository(db_session),
        audit_repo,
        auth_service,
    ), auth_service


@pytest.fixture()
def shift_service(db_session, employee_service):
    _, auth_service = employee_service
    audit_repo = AuditLogRepository(db_session)
    return ShiftService(
        ShiftRepository(db_session),
        NozzleAssignmentRepository(db_session),
        EmployeeRepository(db_session),
        NozzleRepository(db_session),
        UserRepository(db_session),
        audit_repo,
        auth_service,
    )


@pytest.fixture()
def employee_id(employee_service, admin_id):
    service, _ = employee_service
    employee = service.create_employee(
        admin_id,
        EmployeeCreate(first_name="Ravi", last_name="Kumar", contact_number="9876543210", joining_date=date(2026, 1, 1)),
    )
    return employee.id


@pytest.fixture()
def nozzle_id(db_session):
    from app.models.fuel import Fuel

    fuel = Fuel(fuel_type="Petrol", rate_per_liter=100.0, capacity=10000.0, current_stock=5000.0)
    db_session.add(fuel)
    db_session.commit()

    dispenser = Dispenser(code="D1")
    db_session.add(dispenser)
    db_session.commit()

    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel.id, status="active")
    db_session.add(nozzle)
    db_session.commit()
    return nozzle.id


def test_open_button_visible_for_manager_hidden_for_view_only(qapp, shift_service, employee_service, admin_id, accountant_id):
    from app.ui.shift_window import ShiftListWindow

    service, auth_service = employee_service

    admin_window = ShiftListWindow(shift_service, service, auth_service, admin_id)
    assert admin_window.open_button.isHidden() is False

    accountant_window = ShiftListWindow(shift_service, service, auth_service, accountant_id)
    assert accountant_window.open_button.isHidden() is True


def test_shift_list_shows_opened_shifts(qapp, shift_service, employee_service, admin_id):
    from app.ui.shift_window import ShiftListWindow

    service, auth_service = employee_service
    shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))

    window = ShiftListWindow(shift_service, service, auth_service, admin_id)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "Morning"


def test_open_shift_dialog_saves(qapp, shift_service, employee_service, admin_id):
    from app.ui.shift_window import ShiftOpenDialog
    from PySide6.QtWidgets import QDialog

    dialog = ShiftOpenDialog(shift_service, admin_id)
    dialog.label_input.setCurrentText("Evening")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(shift_service.list_shifts(admin_id)) == 1


def test_open_shift_dialog_rejects_duplicate(qapp, shift_service, employee_service, admin_id):
    from app.ui.shift_window import ShiftOpenDialog

    shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 2), shift_label="Morning"))

    dialog = ShiftOpenDialog(shift_service, admin_id)
    from app.ui.qt_utils import date_to_qdate

    dialog.date_input.setDate(date_to_qdate(date(2026, 6, 2)))
    dialog.label_input.setCurrentText("Morning")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_detail_dialog_assign_nozzle_and_close_shift(qapp, shift_service, employee_service, admin_id, employee_id, nozzle_id, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.shift_window import NozzleAssignDialog, ShiftDetailDialog
    from PySide6.QtWidgets import QDialog

    service, auth_service = employee_service
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 3), shift_label="Morning"))

    assign_dialog = NozzleAssignDialog(shift_service, service, admin_id, shift.id)
    assign_dialog.opening_meter_input.setValue(1000.0)
    assign_dialog._save()
    assert assign_dialog.result() == QDialog.Accepted

    detail = ShiftDetailDialog(shift_service, service, auth_service, admin_id, shift.id)
    assert detail.table.rowCount() == 1

    # Closing should be blocked while the assignment is still active
    monkeypatch.setattr("app.ui.shift_window.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    detail._close_shift()
    assert shift_service.get_shift(admin_id, shift.id).status == "open"

    # Complete the assignment (simulate choosing "Yes" then entering a closing meter)
    monkeypatch.setattr(
        "app.ui.shift_window.QInputDialog.getDouble", lambda *a, **k: (1200.0, True)
    )
    detail.table.selectRow(0)
    detail._open_assignment_action()

    assignments = shift_service.list_nozzle_assignments(admin_id, shift.id)
    assert assignments[0].status == "completed"

    detail._close_shift()
    assert shift_service.get_shift(admin_id, shift.id).status == "closed"


def test_reopen_shift_requires_reason_and_permission(qapp, shift_service, employee_service, admin_id, monkeypatch):
    from app.ui.shift_window import ShiftDetailDialog

    service, auth_service = employee_service
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 4), shift_label="Morning"))
    shift_service.close_shift(admin_id, shift.id)

    detail = ShiftDetailDialog(shift_service, service, auth_service, admin_id, shift.id)
    assert detail.reopen_button.isEnabled() is True

    monkeypatch.setattr("app.ui.shift_window.QInputDialog.getText", lambda *a, **k: ("", False))
    detail._reopen_shift()
    assert shift_service.get_shift(admin_id, shift.id).status == "closed"

    monkeypatch.setattr("app.ui.shift_window.QInputDialog.getText", lambda *a, **k: ("Forgot an entry", True))
    detail._reopen_shift()
    assert shift_service.get_shift(admin_id, shift.id).status == "open"
