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


def test_empty_fields_set_validation_error_without_calling_auth(bridge, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("authenticate() must not be called for empty fields")

    monkeypatch.setattr(bridge._auth_service, "authenticate", boom)

    bridge.attempt_login("", "")

    assert "Enter both" in bridge.error


def test_wrong_password_sets_generic_error(bridge):
    succeeded = []
    bridge.loginSucceeded.connect(lambda data: succeeded.append(data))

    bridge.attempt_login("admin", "wrong-password")

    assert bridge.error == "Invalid username or password"
    assert succeeded == []


def test_unexpected_error_during_login_sets_generic_message_not_a_crash(bridge, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(bridge._auth_service, "authenticate", boom)

    bridge.attempt_login("admin", "whatever")  # must not raise

    assert "Something went wrong" in bridge.error


def test_successful_login_clears_error_and_emits_user_data(bridge):
    received = []
    bridge.loginSucceeded.connect(lambda data: received.append(data))

    bridge.attempt_login("admin", DEFAULT_ADMIN_PASSWORD)

    assert bridge.error == ""
    assert len(received) == 1
    assert received[0]["username"] == "admin"
    assert "session_token" in received[0]


def test_busy_flag_is_false_before_and_after_a_login_attempt(bridge):
    # busy toggles true only during the AuthService.authenticate() call
    # itself; by the time attempt_login() returns it must be back to
    # false, or the QML Sign In button would stay disabled forever.
    assert bridge.busy is False
    bridge.attempt_login("admin", DEFAULT_ADMIN_PASSWORD)
    assert bridge.busy is False


def test_error_is_cleared_at_the_start_of_a_new_attempt(bridge):
    bridge.attempt_login("admin", "wrong-password")
    assert bridge.error != ""

    bridge.attempt_login("admin", DEFAULT_ADMIN_PASSWORD)
    assert bridge.error == ""
