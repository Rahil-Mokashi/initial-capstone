from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.database.seed import DEFAULT_ADMIN_PASSWORD, seed_initial_data
from app.models.user import User
from app.repositories.user_session_repository import UserSessionRepository


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_ui.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    seed_initial_data()
    # These tests exercise login/logout/session behavior, not the forced
    # first-login password rotation (that flow has its own dedicated
    # tests) - clear the seeded admin's must_change_password so a modal,
    # un-closable ChangePasswordDialog doesn't block the event loop here.
    session = session_factory()
    admin = session.query(User).filter_by(username="admin").first()
    admin.must_change_password = False
    session.commit()
    session.close()

    return session_factory


@pytest.fixture()
def controller(qapp, seeded_db):
    from app.ui.main_window import AppController

    ctrl = AppController()
    ctrl.start()
    yield ctrl
    # Tear the controller down instead of leaking it.
    #
    # Without this, every test in this module left behind a live database
    # session, a running session timer and a full window tree (each
    # dashboard card carries a QGraphicsDropShadowEffect), because nothing
    # ever closed them. Those accumulate across the module and are a
    # direct contributor to the native-resource crash that makes the full
    # suite fall over - the failure looks random and lands in whichever
    # test happens to allocate once too often, which is why it reads as
    # unrelated to whatever change exposed it.
    ctrl.shutdown()
    qapp.processEvents()  # let deleteLater actually run before the next test


def test_login_window_shown_on_start(controller):
    assert controller.login_window is not None
    assert controller.main_window is None


def test_auth_service_session_timeout_comes_from_settings_not_a_hardcoded_default(controller):
    from app.core.config import settings

    assert controller._auth_service._session_timeout == timedelta(hours=settings.session_timeout_hours)


def test_enter_in_username_moves_focus_to_password_instead_of_submitting(controller, qapp):
    # The login form moved from QWidget to QML (2026-09-02, hybrid QML UI
    # upgrade Phase A) - there is no username_input/password_input widget
    # attribute to read anymore. find_qml_object() reaches into the loaded
    # QML scene by objectName instead (see LoginWindow.find_qml_object),
    # and QTest.keyClick simulates the real Enter keypress the same way a
    # user pressing it in the username field would, exercising
    # LoginScreen.qml's actual onAccepted binding rather than a Python
    # stand-in for it.
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    login_window = controller.login_window
    login_window.activateWindow()
    login_window.raise_()
    qapp.processEvents()

    username_field = login_window.find_qml_object("usernameField")
    password_field = login_window.find_qml_object("passwordField")
    assert username_field is not None and password_field is not None

    username_field.setProperty("text", "admin")
    username_field.forceActiveFocus()
    qapp.processEvents()

    QTest.keyClick(login_window._quick_widget, Qt.Key_Return)
    qapp.processEvents()

    assert controller.main_window is None
    assert password_field.property("activeFocus") is True


def test_real_return_keypress_in_password_field_logs_in_without_crashing(controller, qapp):
    """The actual regression test for the 2026-09-16 crash: every other
    login test in this file (and in test_login_bridge.py) drives
    LoginBridge directly, which never exercises the real path a user's
    keypress takes - QML's Return-key handling -> submitTrigger ->
    Qt.QueuedConnection -> bridge.submit(). That real path is exactly
    what reliably crashed with a native stack overflow before this fix
    (see LoginScreen.qml's and login_window.py's own long comments).
    qapp.processEvents() is required here, unlike _login()'s direct
    calls - the whole point of the fix is that this path is now
    genuinely asynchronous, dispatched only once the event loop gets
    back to its own outermost frame.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    login_window = controller.login_window
    login_window.activateWindow()
    login_window.raise_()
    qapp.processEvents()

    username_field = login_window.find_qml_object("usernameField")
    password_field = login_window.find_qml_object("passwordField")

    username_field.setProperty("text", "admin")
    password_field.setProperty("text", DEFAULT_ADMIN_PASSWORD)
    password_field.forceActiveFocus()
    qapp.processEvents()

    QTest.keyClick(login_window._quick_widget, Qt.Key_Return)
    qapp.processEvents()

    assert controller.main_window is not None
    assert controller.login_window is None


def test_real_sign_in_button_click_logs_in_without_crashing(controller, qapp):
    """Same regression coverage as the Return-key test above, for the
    other real submit path (signInButton.onClicked)."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    login_window = controller.login_window
    login_window.activateWindow()
    login_window.raise_()
    qapp.processEvents()

    username_field = login_window.find_qml_object("usernameField")
    password_field = login_window.find_qml_object("passwordField")
    sign_in_button = login_window.find_qml_object("signInButton")

    username_field.setProperty("text", "admin")
    password_field.setProperty("text", DEFAULT_ADMIN_PASSWORD)
    qapp.processEvents()

    center = sign_in_button.mapToScene(sign_in_button.boundingRect().center())
    QTest.mouseClick(
        login_window._quick_widget, Qt.LeftButton, Qt.NoModifier, QPoint(int(center.x()), int(center.y())),
    )
    qapp.processEvents()

    assert controller.main_window is not None
    assert controller.login_window is None


def _login(controller, username: str, password: str) -> None:
    """Mirrors what LoginScreen.qml's onTextChanged handlers do as the
    user types, then submits directly - equivalent to what actually
    happens once LoginWindow's Qt.QueuedConnection has dispatched a
    real QML submit (2026-09-16 fix: see LoginBridge.submit's and
    LoginScreen.qml's own comments for why QML never calls bridge
    methods directly from onAccepted/onClicked any more)."""
    bridge = controller.login_window.bridge
    bridge.username = username
    bridge.password = password
    bridge.submit()


def test_wrong_password_shows_generic_error_and_stays_on_login(controller):
    _login(controller, "admin", "wrong-password")

    assert controller.main_window is None
    assert controller.login_window.bridge.error == "That username or password isn't correct. Please check and try again."


def test_unexpected_error_during_login_shows_generic_message_not_a_crash(controller, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(controller.login_window.bridge._auth_service, "authenticate", boom)

    _login(controller, "admin", "whatever")  # must not raise

    assert controller.main_window is None
    assert "Something went wrong" in controller.login_window.bridge.error


def test_empty_fields_show_validation_message_without_calling_auth(controller):
    _login(controller, "", "")

    assert controller.main_window is None
    assert "enter both" in controller.login_window.bridge.error.lower()


def test_successful_login_shows_main_window_with_user_info(controller):
    _login(controller, "admin", DEFAULT_ADMIN_PASSWORD)

    assert controller.login_window is None
    assert controller.main_window is not None
    assert controller.main_window._session_token


def test_logout_returns_to_login_window_and_invalidates_session(controller, seeded_db):
    _login(controller, "admin", DEFAULT_ADMIN_PASSWORD)

    token = controller.main_window._session_token
    controller.main_window._logout()

    assert controller.main_window is None
    assert controller.login_window is not None

    session_repo = UserSessionRepository(seeded_db())
    assert session_repo.get_by_token(token) is None


def test_expired_session_triggers_auto_logout(controller, seeded_db, monkeypatch):
    # QMessageBox.information() is modal and blocks on a real display; stub it
    # out so this test can't hang waiting for a click that will never come.
    monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *a, **k: None)

    _login(controller, "admin", DEFAULT_ADMIN_PASSWORD)

    main_window = controller.main_window
    token = main_window._session_token

    db_session = seeded_db()
    session_repo = UserSessionRepository(db_session)
    entry = session_repo.get_by_token(token)
    entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    main_window._check_session()

    assert controller.main_window is None
    assert controller.login_window is not None
