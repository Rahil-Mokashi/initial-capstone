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
    login_window = controller.login_window
    # hasFocus() reflects OS-level window activation, not just Qt's
    # internal focus widget - without this a window that isn't the
    # foreground OS window can report hasFocus() False even after
    # setFocus() actually ran, unrelated to whether the code is correct.
    login_window.activateWindow()
    login_window.raise_()
    qapp.processEvents()

    login_window.username_input.setText("admin")
    login_window.username_input.returnPressed.emit()
    qapp.processEvents()

    assert controller.main_window is None
    assert login_window.password_input.hasFocus() is True


def test_wrong_password_shows_generic_error_and_stays_on_login(controller):
    controller.login_window.username_input.setText("admin")
    controller.login_window.password_input.setText("wrong-password")
    controller.login_window._attempt_login()

    assert controller.main_window is None
    assert controller.login_window.error_label.text() == "Invalid username or password"
    assert controller.login_window.password_input.text() == ""


def test_unexpected_error_during_login_shows_generic_message_not_a_crash(controller, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(controller.login_window._auth_service, "authenticate", boom)

    controller.login_window.username_input.setText("admin")
    controller.login_window.password_input.setText("whatever")
    controller.login_window._attempt_login()  # must not raise

    assert controller.main_window is None
    assert "Something went wrong" in controller.login_window.error_label.text()


def test_empty_fields_show_validation_message_without_calling_auth(controller):
    controller.login_window.username_input.setText("")
    controller.login_window.password_input.setText("")
    controller.login_window._attempt_login()

    assert controller.main_window is None
    assert "Enter both" in controller.login_window.error_label.text()


def test_successful_login_shows_main_window_with_user_info(controller):
    controller.login_window.username_input.setText("admin")
    controller.login_window.password_input.setText(DEFAULT_ADMIN_PASSWORD)
    controller.login_window._attempt_login()

    assert controller.login_window is None
    assert controller.main_window is not None
    assert controller.main_window._session_token


def test_logout_returns_to_login_window_and_invalidates_session(controller, seeded_db):
    controller.login_window.username_input.setText("admin")
    controller.login_window.password_input.setText(DEFAULT_ADMIN_PASSWORD)
    controller.login_window._attempt_login()

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

    controller.login_window.username_input.setText("admin")
    controller.login_window.password_input.setText(DEFAULT_ADMIN_PASSWORD)
    controller.login_window._attempt_login()

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
