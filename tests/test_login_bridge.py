"""LoginBridge (app/ui/login_bridge.py) is the QObject the QML login
screen binds to (app/ui/qml/LoginScreen.qml) - these tests exercise the
same business-facing behavior tests/test_login_ui.py used to assert
directly on QWidget attributes (username_input/password_input/
error_label/_attempt_login) before the login screen moved to QML
(2026-09-02). The QML file itself has no equivalent Python-testable
attributes, so LoginBridge is where this coverage now belongs.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.database.seed import DEFAULT_ADMIN_PASSWORD, seed_initial_data
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
    sqlite_path = str(tmp_path / "test_login_bridge.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def bridge(qapp, db_session):
    from app.ui.login_bridge import LoginBridge

    seed_initial_data()
    auth_service = AuthService(
        UserRepository(db_session),
        AuditLogRepository(db_session),
        UserSessionRepository(db_session),
        session_timeout_hours=8,
    )
    return LoginBridge(auth_service)


def _fill(bridge, username: str, password: str) -> None:
    """Mirrors what LoginScreen.qml's onTextChanged handlers do as the
    user types - setting these properties directly, then calling
    submit() synchronously, is exactly how a real QML-driven call
    behaves once LoginWindow's Qt.QueuedConnection has already
    dispatched it (see LoginBridge.submit's own docstring: submit()
    itself no longer needs to defer anything - the boundary that used
    to crash is now upstream of this class entirely, in how QML/
    LoginWindow reach it)."""
    bridge.username = username
    bridge.password = password


def test_empty_fields_set_validation_error_without_calling_auth(bridge, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("authenticate() must not be called for empty fields")

    monkeypatch.setattr(bridge._auth_service, "authenticate", boom)

    _fill(bridge, "", "")
    bridge.submit()

    assert "enter both" in bridge.error.lower()


def test_wrong_password_sets_generic_error(bridge):
    succeeded = []
    bridge.loginSucceeded.connect(lambda data: succeeded.append(data))

    _fill(bridge, "admin", "wrong-password")
    bridge.submit()

    assert bridge.error == "That username or password isn't correct. Please check and try again."
    assert succeeded == []


def test_unexpected_error_during_login_sets_generic_message_not_a_crash(bridge, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(bridge._auth_service, "authenticate", boom)

    _fill(bridge, "admin", "whatever")
    bridge.submit()  # must not raise

    assert "Something went wrong" in bridge.error


def test_successful_login_clears_error_and_emits_user_data(bridge):
    received = []
    bridge.loginSucceeded.connect(lambda data: received.append(data))

    _fill(bridge, "admin", DEFAULT_ADMIN_PASSWORD)
    bridge.submit()

    assert bridge.error == ""
    assert len(received) == 1
    assert received[0]["username"] == "admin"
    assert "session_token" in received[0]


def test_busy_flag_is_false_before_and_after_a_login_attempt(bridge):
    # busy toggles true only during the AuthService.authenticate() call
    # itself; by the time submit() returns it must be back to false, or
    # the QML Sign In button would stay disabled forever.
    assert bridge.busy is False
    _fill(bridge, "admin", DEFAULT_ADMIN_PASSWORD)
    bridge.submit()
    assert bridge.busy is False


def test_error_is_cleared_at_the_start_of_a_new_attempt(bridge):
    _fill(bridge, "admin", "wrong-password")
    bridge.submit()
    assert bridge.error != ""

    _fill(bridge, "admin", DEFAULT_ADMIN_PASSWORD)
    bridge.submit()
    assert bridge.error == ""


def test_username_and_password_properties_stay_in_sync_with_qml_typing():
    """Not fixture-dependent on auth - just proves the properties
    themselves round-trip and emit their notify signals, the same
    contract LoginScreen.qml's two-way onTextChanged binding relies on."""
    from unittest.mock import MagicMock

    from app.ui.login_bridge import LoginBridge

    bridge = LoginBridge(MagicMock())
    username_changes = []
    password_changes = []
    bridge.usernameChanged.connect(lambda: username_changes.append(bridge.username))
    bridge.passwordChanged.connect(lambda: password_changes.append(bridge.password))

    bridge.username = "a"
    bridge.username = "ad"
    bridge.password = "p"

    assert username_changes == ["a", "ad"]
    assert password_changes == ["p"]
