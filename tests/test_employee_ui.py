from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.employee import EmployeeCreate
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_employee_ui.db")
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
def shift_supervisor_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.SHIFT_SUPERVISOR.value, "supervisor1").id


@pytest.fixture()
def employee_service(db_session):
    user_repo = UserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    session_repo = UserSessionRepository(db_session)
    auth_service = AuthService(user_repo, audit_repo, session_repo)

    employee_repo = EmployeeRepository(db_session)
    document_repo = EmployeeDocumentRepository(db_session)
    role_repo = RoleRepository(db_session)

    return EmployeeService(employee_repo, document_repo, user_repo, role_repo, audit_repo, auth_service), auth_service


def make_employee_data(**overrides) -> EmployeeCreate:
    defaults = dict(
        first_name="Ravi",
        last_name="Kumar",
        contact_number="+91 9876543210",
        joining_date=date(2026, 1, 1),
        designation="Attendant",
        department="Operations",
    )
    defaults.update(overrides)
    return EmployeeCreate(**defaults)


def test_employee_list_shows_created_employees(qapp, employee_service, admin_id):
    from app.ui.employee_window import EmployeeListWindow

    service, auth_service = employee_service
    service.create_employee(admin_id, make_employee_data())
    service.create_employee(admin_id, make_employee_data(first_name="Sita"))

    window = EmployeeListWindow(service, auth_service, admin_id)
    assert window.table.rowCount() == 2

    window.search_input.setText("sita")
    assert window.table.rowCount() == 1


def test_add_button_visible_for_manager_hidden_for_view_only(qapp, employee_service, admin_id, shift_supervisor_id):
    from app.ui.employee_window import EmployeeListWindow

    service, auth_service = employee_service

    admin_window = EmployeeListWindow(service, auth_service, admin_id)
    assert admin_window.add_button.isHidden() is False

    supervisor_window = EmployeeListWindow(service, auth_service, shift_supervisor_id)
    assert supervisor_window.add_button.isHidden() is True


def test_add_employee_dialog_saves_valid_employee(qapp, employee_service, admin_id):
    from app.ui.employee_window import EmployeeFormDialog

    service, _ = employee_service
    dialog = EmployeeFormDialog(service, admin_id)
    dialog.first_name_input.setText("Anita")
    dialog.last_name_input.setText("Sharma")
    dialog.contact_input.setText("9876500000")

    dialog._save()

    from PySide6.QtWidgets import QDialog

    assert dialog.result() == QDialog.Accepted
    assert len(service.list_employees(admin_id)) == 1


def test_add_employee_dialog_shows_error_for_invalid_contact(qapp, employee_service, admin_id):
    from app.ui.employee_window import EmployeeFormDialog

    service, _ = employee_service
    dialog = EmployeeFormDialog(service, admin_id)
    dialog.first_name_input.setText("Anita")
    dialog.last_name_input.setText("Sharma")
    dialog.contact_input.setText("not-a-phone!!")

    dialog._save()

    assert dialog.error_label.isHidden() is False
    assert len(service.list_employees(admin_id)) == 0


def test_detail_dialog_save_profile_updates_employee(qapp, employee_service, admin_id):
    from app.ui.employee_window import EmployeeDetailDialog

    service, _ = employee_service
    employee = service.create_employee(admin_id, make_employee_data())

    dialog = EmployeeDetailDialog(service, admin_id, employee.id, can_manage=True)
    dialog.designation_input.setText("Senior Attendant")
    dialog._save_profile()

    assert service.get_employee(admin_id, employee.id).designation == "Senior Attendant"


def test_detail_dialog_status_change(qapp, employee_service, admin_id, monkeypatch):
    from app.ui.employee_window import EmployeeDetailDialog

    monkeypatch.setattr("app.ui.employee_window.QInputDialog.getText", lambda *a, **k: ("Medical leave", True))

    service, _ = employee_service
    employee = service.create_employee(admin_id, make_employee_data())

    dialog = EmployeeDetailDialog(service, admin_id, employee.id, can_manage=True)
    dialog.status_combo.setCurrentText("on_leave")
    dialog._apply_status_change()

    assert service.get_employee(admin_id, employee.id).status == "on_leave"


def test_detail_dialog_record_exit_requires_confirmation(qapp, employee_service, admin_id, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.employee_window import EmployeeDetailDialog

    service, _ = employee_service
    employee = service.create_employee(admin_id, make_employee_data())
    dialog = EmployeeDetailDialog(service, admin_id, employee.id, can_manage=True)

    monkeypatch.setattr("app.ui.employee_window.QMessageBox.question", lambda *a, **k: QMessageBox.No)
    dialog._record_exit()
    assert service.get_employee(admin_id, employee.id).status != "terminated"

    monkeypatch.setattr("app.ui.employee_window.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr("app.ui.employee_window.QInputDialog.getText", lambda *a, **k: ("Resigned", True))
    dialog._record_exit()
    assert service.get_employee(admin_id, employee.id).status == "terminated"


def test_detail_dialog_add_and_remove_document(qapp, employee_service, admin_id, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.employee_window import EmployeeDetailDialog

    service, _ = employee_service
    employee = service.create_employee(admin_id, make_employee_data())
    dialog = EmployeeDetailDialog(service, admin_id, employee.id, can_manage=True)

    monkeypatch.setattr(
        "app.ui.employee_window.QFileDialog.getOpenFileName", lambda *a, **k: ("/docs/id.pdf", "")
    )
    monkeypatch.setattr("app.ui.employee_window.QInputDialog.getText", lambda *a, **k: ("ID Proof", True))
    dialog._add_document()
    assert dialog.documents_list.count() == 1

    dialog.documents_list.setCurrentRow(0)
    monkeypatch.setattr("app.ui.employee_window.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr("app.ui.employee_window.QInputDialog.getText", lambda *a, **k: ("Wrong file", True))
    dialog._remove_selected_document()
    assert dialog.documents_list.count() == 0


def test_detail_dialog_disables_manage_actions_for_view_only(qapp, employee_service, admin_id):
    from app.ui.employee_window import EmployeeDetailDialog

    service, _ = employee_service
    employee = service.create_employee(admin_id, make_employee_data())

    dialog = EmployeeDetailDialog(service, admin_id, employee.id, can_manage=False)

    assert dialog.save_profile_button.isEnabled() is False
    assert dialog.apply_status_button.isEnabled() is False
    assert dialog.exit_button.isEnabled() is False
    assert dialog.add_document_button.isEnabled() is False
    assert dialog.remove_document_button.isEnabled() is False
