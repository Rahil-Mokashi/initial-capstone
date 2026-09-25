"""app/ui/lock_screen_dialog.py: resuming a session (Lock) vs. ending
one (Logout) - the dialog must accept the right credential, must reject
a wrong one, must never silently fall through to Windows Hello, and
"Sign Out Instead" must be the one way out since Escape/close are
deliberately disabled (mirrors the forced-mode reasoning in
tests/test_change_password_ui.py).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.database.seed import DEFAULT_ADMIN_PASSWORD, seed_initial_data
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_lock_screen_ui.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def auth_service_and_user_data(db_session):
    seed_initial_data()
    auth_service = AuthService(
        UserRepository(db_session), AuditLogRepository(db_session), UserSessionRepository(db_session)
    )
    success, user_data, _ = auth_service.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
    assert success is True
    return auth_service, user_data


def test_unlock_with_correct_password_accepts(qapp, auth_service_and_user_data):
    from app.ui.lock_screen_dialog import LockScreenDialog
    from PySide6.QtWidgets import QDialog

    auth_service, user_data = auth_service_and_user_data
    dialog = LockScreenDialog(auth_service, user_data)
    dialog.credential_input.setText(DEFAULT_ADMIN_PASSWORD)
    dialog._unlock()

    assert dialog.result() == QDialog.Accepted
    assert dialog.signed_out is False


def test_unlock_with_wrong_password_shows_error_and_does_not_accept(qapp, auth_service_and_user_data):
    from app.ui.lock_screen_dialog import LockScreenDialog
    from PySide6.QtWidgets import QDialog

    auth_service, user_data = auth_service_and_user_data
    dialog = LockScreenDialog(auth_service, user_data)
    dialog.credential_input.setText("wrong-password")
    dialog._unlock()

    assert dialog.result() != QDialog.Accepted
    assert dialog.error_label.isHidden() is False


def test_sign_out_instead_sets_flag_and_accepts(qapp, auth_service_and_user_data):
    from app.ui.lock_screen_dialog import LockScreenDialog
    from PySide6.QtWidgets import QDialog

    auth_service, user_data = auth_service_and_user_data
    dialog = LockScreenDialog(auth_service, user_data)
    dialog._sign_out_instead()

    assert dialog.result() == QDialog.Accepted
    assert dialog.signed_out is True


def test_reject_and_close_are_both_disabled(qapp, auth_service_and_user_data):
    from app.ui.lock_screen_dialog import LockScreenDialog

    auth_service, user_data = auth_service_and_user_data
    dialog = LockScreenDialog(auth_service, user_data)
    dialog.show()
    qapp.processEvents()

    dialog.reject()
    qapp.processEvents()
    assert dialog.isVisible() is True

    dialog.close()
    qapp.processEvents()
    assert dialog.isVisible() is True
    dialog.hide()


def test_pin_toggle_only_shown_when_user_has_a_pin(qapp, auth_service_and_user_data):
    from app.ui.lock_screen_dialog import LockScreenDialog
    from PySide6.QtWidgets import QPushButton

    auth_service, user_data = auth_service_and_user_data
    dialog = LockScreenDialog(auth_service, dict(user_data, has_pin=False))
    button_texts = [b.text() for b in dialog.findChildren(QPushButton)]
    assert "Use PIN instead" not in button_texts

    dialog_with_pin = LockScreenDialog(auth_service, dict(user_data, has_pin=True))
    button_texts_with_pin = [b.text() for b in dialog_with_pin.findChildren(QPushButton)]
    assert "Use PIN instead" in button_texts_with_pin


def test_windows_hello_button_hidden_when_unavailable(qapp, auth_service_and_user_data, monkeypatch):
    import app.ui.lock_screen_dialog as lock_screen_module
    from PySide6.QtWidgets import QPushButton

    monkeypatch.setattr(lock_screen_module.windows_hello, "is_available", lambda: False)
    auth_service, user_data = auth_service_and_user_data
    dialog = lock_screen_module.LockScreenDialog(auth_service, user_data)

    button_texts = [b.text() for b in dialog.findChildren(QPushButton)]
    assert "Unlock with Windows Hello" not in button_texts


def test_windows_hello_button_shown_and_unlocks_when_available(qapp, auth_service_and_user_data, monkeypatch):
    import app.ui.lock_screen_dialog as lock_screen_module
    from PySide6.QtWidgets import QDialog

    monkeypatch.setattr(lock_screen_module.windows_hello, "is_available", lambda: True)
    monkeypatch.setattr(lock_screen_module.windows_hello, "verify", lambda *a, **k: True)
    auth_service, user_data = auth_service_and_user_data
    dialog = lock_screen_module.LockScreenDialog(auth_service, user_data)

    dialog._unlock_with_windows_hello()
    assert dialog.result() == QDialog.Accepted


def test_reauthenticate_failures_count_toward_the_account_lockout(qapp, auth_service_and_user_data, db_session):
    """The Lock Screen must not be a second, unlimited-guess surface
    against the account - AuthService.reauthenticate shares the same
    lockout as a fresh sign-in (see its own docstring)."""
    from app.core.constants import MAX_FAILED_LOGIN_ATTEMPTS
    from app.ui.lock_screen_dialog import LockScreenDialog

    auth_service, user_data = auth_service_and_user_data
    for _ in range(MAX_FAILED_LOGIN_ATTEMPTS):
        dialog = LockScreenDialog(auth_service, user_data)
        dialog.credential_input.setText("wrong-password")
        dialog._unlock()

    admin = db_session.query(User).filter_by(username="admin").first()
    assert admin.is_locked is True
