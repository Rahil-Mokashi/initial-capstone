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
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService
from app.services.user_service import UserService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_user_management_ui.db")
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
def role_repo(db_session):
    return RoleRepository(db_session)


@pytest.fixture()
def attendant_role_id(db_session):
    seed_initial_data()
    return db_session.query(Role).filter_by(name=UserRole.ATTENDANT.value).first().id


@pytest.fixture()
def user_service_and_auth(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    service = UserService(UserRepository(db_session), RoleRepository(db_session), audit_repo, auth_service)
    return service, auth_service


def test_add_button_visible_for_admin(qapp, user_service_and_auth, role_repo, admin_id):
    from app.ui.user_management_window import UserListWindow

    service, _ = user_service_and_auth
    window = UserListWindow(service, role_repo, admin_id)
    assert window.add_button.isHidden() is False


def test_list_window_shows_seeded_admin_user(qapp, user_service_and_auth, role_repo, admin_id):
    from app.ui.user_management_window import UserListWindow

    service, _ = user_service_and_auth
    window = UserListWindow(service, role_repo, admin_id)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 0).text() == "admin"


def test_form_dialog_creates_user_for_selected_role(qapp, user_service_and_auth, role_repo, admin_id, attendant_role_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.user_management_window import UserFormDialog

    service, _ = user_service_and_auth
    dialog = UserFormDialog(service, role_repo, admin_id)
    dialog.username_input.setText("new.attendant")
    dialog.email_input.setText("new.attendant@example.com")
    dialog.password_input.setText("Strong@123")
    index = dialog.role_combo.findData(attendant_role_id)
    dialog.role_combo.setCurrentIndex(index)
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    users = service.list_users(admin_id)
    assert any(user.username == "new.attendant" and user.role_id == attendant_role_id for user in users)


def test_enter_key_advances_through_form_fields_instead_of_submitting_early(qapp, user_service_and_auth, role_repo, admin_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.user_management_window import UserFormDialog

    service, _ = user_service_and_auth
    dialog = UserFormDialog(service, role_repo, admin_id)
    dialog.show()
    qapp.processEvents()

    dialog.username_input.setText("new.attendant")
    dialog.username_input.returnPressed.emit()
    assert dialog.email_input.hasFocus() is True
    assert dialog.result() != QDialog.Accepted

    dialog.email_input.setText("new.attendant@example.com")
    dialog.email_input.returnPressed.emit()
    assert dialog.first_name_input.hasFocus() is True


def test_form_dialog_shows_error_for_weak_password(qapp, user_service_and_auth, role_repo, admin_id, attendant_role_id):
    from app.ui.user_management_window import UserFormDialog

    service, _ = user_service_and_auth
    dialog = UserFormDialog(service, role_repo, admin_id)
    dialog.username_input.setText("new.attendant")
    dialog.email_input.setText("new.attendant@example.com")
    dialog.password_input.setText("weak")
    index = dialog.role_combo.findData(attendant_role_id)
    dialog.role_combo.setCurrentIndex(index)
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_form_dialog_shows_error_for_duplicate_username(qapp, user_service_and_auth, role_repo, admin_id, attendant_role_id):
    from app.ui.user_management_window import UserFormDialog

    service, _ = user_service_and_auth
    service.create_user(
        admin_id,
        UserCreate(username="taken", email="taken@example.com", password="Strong@123", role_id=attendant_role_id),
    )

    dialog = UserFormDialog(service, role_repo, admin_id)
    dialog.username_input.setText("taken")
    dialog.email_input.setText("other@example.com")
    dialog.password_input.setText("Strong@123")
    index = dialog.role_combo.findData(attendant_role_id)
    dialog.role_combo.setCurrentIndex(index)
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_detail_dialog_deactivates_and_reactivates_user(qapp, user_service_and_auth, role_repo, admin_id, attendant_role_id):
    from app.ui.user_management_window import UserDetailDialog

    service, _ = user_service_and_auth
    user = service.create_user(
        admin_id,
        UserCreate(username="attendant.a", email="a@example.com", password="Strong@123", role_id=attendant_role_id),
    )

    dialog = UserDetailDialog(service, role_repo, admin_id, user.id)
    assert dialog.toggle_active_button.text() == "Deactivate"

    service.set_user_active(admin_id, user.id, False, "No longer employed")
    dialog._refresh()
    assert dialog.toggle_active_button.text() == "Activate"
    assert dialog.status_label.text() == "Status: Inactive"


def test_detail_dialog_unlock_button_enabled_only_when_locked(qapp, user_service_and_auth, role_repo, admin_id, attendant_role_id, db_session):
    from app.ui.user_management_window import UserDetailDialog

    service, _ = user_service_and_auth
    user = service.create_user(
        admin_id,
        UserCreate(username="attendant.b", email="b@example.com", password="Strong@123", role_id=attendant_role_id),
    )

    dialog = UserDetailDialog(service, role_repo, admin_id, user.id)
    assert dialog.unlock_button.isEnabled() is False

    db_user = db_session.query(User).filter_by(id=user.id).first()
    db_user.is_locked = True
    db_session.commit()

    dialog._refresh()
    assert dialog.unlock_button.isEnabled() is True
