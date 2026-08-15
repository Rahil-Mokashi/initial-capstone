from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.database.seed import DEFAULT_ADMIN_PASSWORD, seed_initial_data
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
    return session_factory


@pytest.fixture()
def controller(qapp, seeded_db):
    from app.ui.main_window import AppController

    ctrl = AppController()
    ctrl.start()
    yield ctrl


def test_login_window_shown_on_start(controller):
    assert controller.login_window is not None
    assert controller.main_window is None


def test_wrong_password_shows_generic_error_and_stays_on_login(controller):
    controller.login_window.username_input.setText("admin")
    controller.login_window.password_input.setText("wrong-password")
    controller.login_window._attempt_login()

    assert controller.main_window is None
    assert controller.login_window.error_label.text() == "Invalid username or password"
    assert controller.login_window.password_input.text() == ""


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
