import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService
from app.services.user_service import UserService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_change_password_ui.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def attendant(db_session):
    seed_initial_data()
    role = db_session.query(Role).filter_by(name=UserRole.ATTENDANT.value).first()
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    user_service = UserService(UserRepository(db_session), RoleRepository(db_session), audit_repo, auth_service)
    from app.schemas.user import UserCreate

    admin_id = db_session.query(User).filter_by(username="admin").first().id
    user = user_service.create_user(
        admin_id,
        UserCreate(username="attendant1", email="attendant1@example.com", password="Strong@123", role_id=role.id),
    )
    return user_service, user.id


def test_dialog_accepts_a_valid_password_change(qapp, attendant):
    from app.ui.change_password_dialog import ChangePasswordDialog
    from PySide6.QtWidgets import QDialog

    user_service, user_id = attendant
    dialog = ChangePasswordDialog(user_service, user_id, forced=False)
    dialog.current_password_input.setText("Strong@123")
    dialog.new_password_input.setText("EvenStronger@456")
    dialog.confirm_password_input.setText("EvenStronger@456")
    dialog._save()

    assert dialog.result() == QDialog.Accepted


def test_dialog_shows_error_on_wrong_current_password(qapp, attendant):
    from app.ui.change_password_dialog import ChangePasswordDialog

    user_service, user_id = attendant
    dialog = ChangePasswordDialog(user_service, user_id, forced=False)
    dialog.current_password_input.setText("wrong-password")
    dialog.new_password_input.setText("EvenStronger@456")
    dialog.confirm_password_input.setText("EvenStronger@456")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_dialog_shows_error_when_confirmation_does_not_match(qapp, attendant):
    from app.ui.change_password_dialog import ChangePasswordDialog

    user_service, user_id = attendant
    dialog = ChangePasswordDialog(user_service, user_id, forced=False)
    dialog.current_password_input.setText("Strong@123")
    dialog.new_password_input.setText("EvenStronger@456")
    dialog.confirm_password_input.setText("Something@Else9")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_forced_dialog_cannot_be_rejected_or_closed(qapp, attendant):
    from app.ui.change_password_dialog import ChangePasswordDialog

    user_service, user_id = attendant
    dialog = ChangePasswordDialog(user_service, user_id, forced=True)
    dialog.show()
    qapp.processEvents()
    assert dialog.isVisible() is True

    dialog.reject()
    qapp.processEvents()
    assert dialog.isVisible() is True

    dialog.close()
    qapp.processEvents()
    assert dialog.isVisible() is True
    dialog.hide()


def test_non_forced_dialog_can_be_rejected(qapp, attendant):
    from app.ui.change_password_dialog import ChangePasswordDialog

    user_service, user_id = attendant
    dialog = ChangePasswordDialog(user_service, user_id, forced=False)
    dialog.show()
    qapp.processEvents()

    dialog.reject()
    qapp.processEvents()
    assert dialog.isVisible() is False


def test_forced_dialog_has_no_cancel_button(qapp, attendant):
    from app.ui.change_password_dialog import ChangePasswordDialog

    user_service, user_id = attendant
    dialog = ChangePasswordDialog(user_service, user_id, forced=True)

    from PySide6.QtWidgets import QPushButton

    button_texts = [b.text() for b in dialog.findChildren(QPushButton)]
    assert "Cancel" not in button_texts


def test_app_controller_shows_forced_dialog_then_main_window(qapp, db_session, monkeypatch):
    """Regression test for the exact hang risk this feature introduces:
    AppController._show_main_window must show the forced dialog (not a
    real blocking exec() in this test - we drive it to acceptance
    ourselves) and only then create MainWindow, with the returned
    user_data no longer flagging must_change_password."""
    from app.ui.change_password_dialog import ChangePasswordDialog
    from app.ui.main_window import AppController

    seed_initial_data()
    admin = db_session.query(User).filter_by(username="admin").first()
    assert admin.must_change_password is True

    def fake_exec(self):
        self.current_password_input.setText("Admin@123")
        self.new_password_input.setText("NewAdmin@456")
        self.confirm_password_input.setText("NewAdmin@456")
        self._save()
        return self.result()

    monkeypatch.setattr(ChangePasswordDialog, "exec", fake_exec)

    controller = AppController()
    success, user_data, _ = controller._auth_service.authenticate("admin", "Admin@123")
    assert success is True
    assert user_data["must_change_password"] is True

    controller._show_login()
    controller._show_main_window(user_data)

    assert controller.main_window is not None

    # AppController runs on its own SQLAlchemy session; the fixture's
    # session won't see that session's commit without an explicit
    # refresh, since expire_on_commit=False leaves cached attributes in
    # place until asked to re-read.
    db_session.expire_all()
    refreshed_admin = db_session.query(User).filter_by(username="admin").first()
    assert refreshed_admin.must_change_password is False
