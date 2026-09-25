"""app/ui/set_pin_dialog.py (self-service quick-sign-in PIN) and
app/ui/forgot_password_dialog.py (self-service completion of an
admin-generated password reset code) - the two new credential dialogs
added alongside PIN-based quick sign-in.
"""

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
    sqlite_path = str(tmp_path / "test_pin_and_reset_dialogs_ui.db")
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
    admin_id = db_session.query(User).filter_by(username="admin").first().id
    user = user_service.create_user(
        admin_id,
        UserCreate(username="attendant1", email="attendant1@example.com", password="Strong@123", role_id=role.id),
    )
    return user_service, user.id


# --- SetPinDialog -----------------------------------------------------------


def test_set_pin_dialog_accepts_a_valid_pin(qapp, attendant):
    from app.ui.set_pin_dialog import SetPinDialog
    from PySide6.QtWidgets import QDialog

    user_service, user_id = attendant
    dialog = SetPinDialog(user_service, user_id)
    dialog.current_password_input.setText("Strong@123")
    dialog.pin_input.setText("482913")
    dialog.confirm_pin_input.setText("482913")
    dialog._save()

    assert dialog.result() == QDialog.Accepted


def test_set_pin_dialog_shows_error_on_wrong_current_password(qapp, attendant):
    from app.ui.set_pin_dialog import SetPinDialog

    user_service, user_id = attendant
    dialog = SetPinDialog(user_service, user_id)
    dialog.current_password_input.setText("wrong-password")
    dialog.pin_input.setText("482913")
    dialog.confirm_pin_input.setText("482913")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_set_pin_dialog_shows_error_when_confirmation_does_not_match(qapp, attendant):
    from app.ui.set_pin_dialog import SetPinDialog

    user_service, user_id = attendant
    dialog = SetPinDialog(user_service, user_id)
    dialog.current_password_input.setText("Strong@123")
    dialog.pin_input.setText("482913")
    dialog.confirm_pin_input.setText("111111")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_set_pin_dialog_shows_error_on_weak_pin(qapp, attendant):
    from app.ui.set_pin_dialog import SetPinDialog

    user_service, user_id = attendant
    dialog = SetPinDialog(user_service, user_id)
    dialog.current_password_input.setText("Strong@123")
    dialog.pin_input.setText("111111")
    dialog.confirm_pin_input.setText("111111")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_set_pin_dialog_input_rejects_non_digit_characters(qapp, attendant):
    """The QLineEdit validator itself, not the service - typing a letter
    must simply not appear in the field, the same way a numeric PIN pad
    would behave."""
    from app.ui.set_pin_dialog import SetPinDialog
    from PySide6.QtGui import QValidator

    user_service, user_id = attendant
    dialog = SetPinDialog(user_service, user_id)
    validator = dialog.pin_input.validator()

    state, _text, _pos = validator.validate("12a34", 5)
    assert state != QValidator.Acceptable


# --- ForgotPasswordDialog ----------------------------------------------------


def test_forgot_password_dialog_accepts_a_valid_code(qapp, attendant, db_session):
    from app.ui.forgot_password_dialog import ForgotPasswordDialog
    from PySide6.QtWidgets import QDialog

    user_service, user_id = attendant
    # generate_password_reset_code requires USER_MANAGE - use the seeded
    # admin as the actor generating a code for the attendant.
    admin_id = db_session.query(User).filter_by(username="admin").first().id
    code = user_service.generate_password_reset_code(admin_id, user_id, "Forgot password, night shift")

    dialog = ForgotPasswordDialog(user_service)
    user = user_service._get_user_or_raise(user_id)
    dialog.username_input.setText(user.username)
    dialog.code_input.setText(code)
    dialog.new_password_input.setText("BrandNew@123")
    dialog.confirm_password_input.setText("BrandNew@123")
    dialog._submit()

    assert dialog.result() == QDialog.Accepted


def test_forgot_password_dialog_shows_error_on_wrong_code(qapp, attendant):
    from app.ui.forgot_password_dialog import ForgotPasswordDialog

    user_service, user_id = attendant
    user = user_service._get_user_or_raise(user_id)

    dialog = ForgotPasswordDialog(user_service)
    dialog.username_input.setText(user.username)
    dialog.code_input.setText("00000000")
    dialog.new_password_input.setText("BrandNew@123")
    dialog.confirm_password_input.setText("BrandNew@123")
    dialog._submit()

    assert dialog.error_label.isHidden() is False


def test_forgot_password_dialog_shows_error_when_confirmation_does_not_match(qapp, attendant):
    from app.ui.forgot_password_dialog import ForgotPasswordDialog

    user_service, user_id = attendant
    user = user_service._get_user_or_raise(user_id)

    dialog = ForgotPasswordDialog(user_service)
    dialog.username_input.setText(user.username)
    dialog.code_input.setText("00000000")
    dialog.new_password_input.setText("BrandNew@123")
    dialog.confirm_password_input.setText("Different@456")
    dialog._submit()

    assert dialog.error_label.isHidden() is False
