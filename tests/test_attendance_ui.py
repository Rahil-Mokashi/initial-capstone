from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import AttendanceStatus, UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.user import User
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.employee import EmployeeCreate
from app.services.attendance_service import AttendanceService
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.ui.qt_utils import date_to_qdate


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_attendance_ui.db")
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
def attendance_service(db_session, employee_service):
    service, auth_service = employee_service
    audit_repo = AuditLogRepository(db_session)
    return AttendanceService(AttendanceRepository(db_session), EmployeeRepository(db_session), audit_repo, auth_service)


@pytest.fixture()
def employee_id(employee_service, admin_id):
    service, _ = employee_service
    employee = service.create_employee(
        admin_id,
        EmployeeCreate(first_name="Ravi", last_name="Kumar", contact_number="9876543210", joining_date=date(2026, 1, 1)),
    )
    return employee.id


def test_mark_button_visible_for_manager_hidden_for_view_only(qapp, attendance_service, employee_service, admin_id, accountant_id):
    from app.ui.attendance_window import AttendanceWindow

    service, auth_service = employee_service

    admin_window = AttendanceWindow(attendance_service, service, auth_service, admin_id)
    assert admin_window.mark_button.isHidden() is False

    accountant_window = AttendanceWindow(attendance_service, service, auth_service, accountant_id)
    assert accountant_window.mark_button.isHidden() is True


def test_window_shows_records_marked_for_selected_date(qapp, attendance_service, employee_service, admin_id, employee_id):
    from app.ui.attendance_window import AttendanceWindow
    from app.schemas.attendance import AttendanceMark

    service, auth_service = employee_service
    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 4, 1), status=AttendanceStatus.PRESENT),
    )

    window = AttendanceWindow(attendance_service, service, auth_service, admin_id)
    window.date_input.setDate(date_to_qdate(date(2026, 4, 1)))
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "Present"

    window.date_input.setDate(date_to_qdate(date(2026, 4, 2)))
    assert window.table.rowCount() == 0


def test_mark_dialog_saves_valid_attendance(qapp, attendance_service, employee_service, admin_id, employee_id):
    from app.ui.attendance_window import AttendanceMarkDialog
    from PySide6.QtWidgets import QDialog

    service, _ = employee_service
    dialog = AttendanceMarkDialog(attendance_service, service, admin_id, date_to_qdate(date(2026, 5, 1)))
    dialog.status_combo.setCurrentText(AttendanceStatus.ABSENT.value)

    dialog._save()

    assert dialog.result() == QDialog.Accepted
    records = attendance_service.list_for_date(admin_id, date(2026, 5, 1))
    assert len(records) == 1
    assert records[0].status == AttendanceStatus.ABSENT.value


def test_mark_dialog_rejects_duplicate_for_same_day(qapp, attendance_service, employee_service, admin_id, employee_id):
    from app.ui.attendance_window import AttendanceMarkDialog
    from app.schemas.attendance import AttendanceMark

    attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 5, 2), status=AttendanceStatus.PRESENT),
    )

    service, _ = employee_service
    dialog = AttendanceMarkDialog(attendance_service, service, admin_id, date_to_qdate(date(2026, 5, 2)))
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_correction_dialog_requires_reason(qapp, attendance_service, employee_service, admin_id, employee_id):
    from app.ui.attendance_window import AttendanceCorrectionDialog
    from app.schemas.attendance import AttendanceMark

    record = attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 5, 3), status=AttendanceStatus.ABSENT),
    )

    dialog = AttendanceCorrectionDialog(attendance_service, admin_id, record.id, True)
    dialog.status_combo.setCurrentText(AttendanceStatus.PRESENT.value)
    dialog.reason_input.setPlainText("")
    dialog._save()

    assert dialog.error_label.isHidden() is False
    assert attendance_service.get_attendance(admin_id, record.id).status == AttendanceStatus.ABSENT.value


def test_correction_dialog_saves_with_reason(qapp, attendance_service, employee_service, admin_id, employee_id):
    from app.ui.attendance_window import AttendanceCorrectionDialog
    from app.schemas.attendance import AttendanceMark
    from PySide6.QtWidgets import QDialog

    record = attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 5, 4), status=AttendanceStatus.ABSENT),
    )

    dialog = AttendanceCorrectionDialog(attendance_service, admin_id, record.id, True)
    dialog.status_combo.setCurrentText(AttendanceStatus.PRESENT.value)
    dialog.reason_input.setPlainText("Was actually present")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert attendance_service.get_attendance(admin_id, record.id).status == AttendanceStatus.PRESENT.value


def test_correction_dialog_disables_editing_for_view_only(qapp, attendance_service, employee_service, admin_id, employee_id):
    from app.ui.attendance_window import AttendanceCorrectionDialog
    from app.schemas.attendance import AttendanceMark

    record = attendance_service.mark_attendance(
        admin_id,
        AttendanceMark(employee_id=employee_id, attendance_date=date(2026, 5, 5), status=AttendanceStatus.PRESENT),
    )

    dialog = AttendanceCorrectionDialog(attendance_service, admin_id, record.id, can_manage=False)
    assert dialog.status_combo.isEnabled() is False
    assert dialog.overtime_input.isEnabled() is False
    assert dialog.reason_input.isEnabled() is False
    assert dialog.save_button.isEnabled() is False
