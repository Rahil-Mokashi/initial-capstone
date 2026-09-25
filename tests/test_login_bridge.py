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
def isolated_settings(monkeypatch):
    """Points app.ui.theme's and app.ui.terminal_settings' QSettings at a
    throwaway in-memory store instead of the real per-machine one (the
    Windows registry) - the same isolation tests/test_theme.py already
    applies to theme.py, extended here to cover terminal_settings.py too
    since LoginBridge now reads/writes both."""
    import app.ui.terminal_settings as terminal_settings_module
    import app.ui.theme as theme_module

    store: dict[str, object] = {}

    class FakeSettings:
        def value(self, key, default=None, type=None):  # noqa: A002 - matches QSettings' own signature
            value = store.get(key, default)
            return type(value) if type is not None else value

        def setValue(self, key, value):  # noqa: N802 - matches QSettings' own method name
            store[key] = value

    monkeypatch.setattr(theme_module, "QSettings", lambda *a, **k: FakeSettings())
    monkeypatch.setattr(terminal_settings_module, "QSettings", lambda *a, **k: FakeSettings())
    return store


@pytest.fixture()
def bridge(qapp, db_session, isolated_settings):
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


def test_wrong_password_sets_attempts_remaining(bridge):
    _fill(bridge, "admin", "wrong-password")
    bridge.submit()

    assert bridge.attemptsRemaining == 4  # MAX_FAILED_LOGIN_ATTEMPTS (5) - 1


def test_attempts_remaining_resets_at_the_start_of_a_new_submit(bridge):
    _fill(bridge, "admin", "wrong-password")
    bridge.submit()
    assert bridge.attemptsRemaining == 4

    _fill(bridge, "", "")
    bridge.submit()  # the empty-fields path never even reaches AuthService

    assert bridge.attemptsRemaining == -1


def test_lockout_sets_a_positive_countdown(bridge):
    from app.core.constants import MAX_FAILED_LOGIN_ATTEMPTS

    for _ in range(MAX_FAILED_LOGIN_ATTEMPTS):
        _fill(bridge, "admin", "wrong-password")
        bridge.submit()

    assert "locked" in bridge.error
    assert bridge.lockoutSecondsRemaining > 0


def test_successful_login_records_the_username_on_this_terminal(bridge):
    from app.ui.terminal_settings import get_recent_usernames

    _fill(bridge, "admin", DEFAULT_ADMIN_PASSWORD)
    bridge.submit()

    assert get_recent_usernames() == ["admin"]


def test_failed_login_does_not_record_the_username(bridge):
    from app.ui.terminal_settings import get_recent_usernames

    _fill(bridge, "admin", "wrong-password")
    bridge.submit()

    assert get_recent_usernames() == []


def test_recent_usernames_property_reflects_this_terminals_history(bridge):
    from app.ui.terminal_settings import record_recent_username

    record_recent_username("night-shift-attendant")

    assert bridge.recentUsernames == ["night-shift-attendant"]


def test_toggle_dark_mode_flips_and_persists(bridge):
    from app.ui.theme import is_dark_mode

    starting = bridge.darkMode
    assert starting is is_dark_mode()

    changes = []
    bridge.darkModeChanged.connect(lambda: changes.append(bridge.darkMode))
    bridge.toggleDarkMode()

    assert bridge.darkMode is (not starting)
    assert changes == [not starting]
    # Persisted through the same store the main window's theme toggle
    # uses, so the choice carries over after logging in - not undone the
    # moment this screen closes.
    assert is_dark_mode() is (not starting)


def test_caps_lock_property_reflects_os_state_at_construction(qapp, db_session, isolated_settings, monkeypatch):
    import app.ui.login_bridge as login_bridge_module

    monkeypatch.setattr(login_bridge_module, "is_caps_lock_on", lambda: True)

    seed_initial_data()
    auth_service = AuthService(
        UserRepository(db_session),
        AuditLogRepository(db_session),
        UserSessionRepository(db_session),
        session_timeout_hours=8,
    )
    bridge = login_bridge_module.LoginBridge(auth_service)

    assert bridge.capsLockOn is True


def test_caps_lock_poll_emits_only_on_a_real_change(qapp, db_session, isolated_settings, monkeypatch):
    import app.ui.login_bridge as login_bridge_module

    # Fixed to False at construction, rather than trusting whatever the
    # real machine running this test happens to have Caps Lock set to -
    # that would make the test's outcome depend on the test runner's own
    # physical keyboard state, which is exactly the kind of flakiness a
    # test must not have.
    monkeypatch.setattr(login_bridge_module, "is_caps_lock_on", lambda: False)
    seed_initial_data()
    auth_service = AuthService(
        UserRepository(db_session),
        AuditLogRepository(db_session),
        UserSessionRepository(db_session),
        session_timeout_hours=8,
    )
    bridge = login_bridge_module.LoginBridge(auth_service)
    assert bridge.capsLockOn is False

    changes = []
    bridge.capsLockOnChanged.connect(lambda: changes.append(bridge.capsLockOn))

    monkeypatch.setattr(login_bridge_module, "is_caps_lock_on", lambda: False)
    bridge.pollCapsLock()
    assert changes == []  # no change, no signal

    monkeypatch.setattr(login_bridge_module, "is_caps_lock_on", lambda: True)
    bridge.pollCapsLock()
    assert changes == [True]


def test_device_name_property_is_non_empty(bridge):
    assert bridge.deviceName


def test_initial_login_locale_defaults_to_english(bridge):
    assert bridge.initialLoginLocale == "en"


def test_set_login_locale_persists_through_terminal_settings(bridge):
    from app.ui.terminal_settings import get_login_locale

    bridge.setLoginLocale("hi")
    assert get_login_locale() == "hi"


def test_pin_mode_routes_submit_to_authenticate_with_pin(bridge):
    calls = []
    bridge._auth_service.authenticate_with_pin = lambda *a, **k: (calls.append((a, k)) or (False, None, "no pin"))

    bridge.setPinMode(True)
    bridge.username = "admin"
    bridge.pin = "482913"
    bridge.submit()

    assert len(calls) == 1
    assert calls[0][0][0] == "admin"
    assert calls[0][0][1] == "482913"


def test_password_mode_ignores_pin_field(bridge):
    calls = []
    bridge._auth_service.authenticate = lambda *a, **k: (calls.append(a) or (False, None, "wrong"))

    bridge.setPinMode(False)
    bridge.username = "admin"
    bridge.password = "Admin@123"
    bridge.pin = "482913"  # left over from a mode switch - must be ignored
    bridge.submit()

    assert calls[0][1] == "Admin@123"
