"""Catches QML syntax/binding mistakes in LoginScreen.qml / Theme.qml
that a normal pytest run wouldn't otherwise surface - constructing
LoginWindow only fails loudly if the .qml file can't be found at all;
a typo inside a valid file still "loads" (QQuickWidget.Status.Error) but
would only be noticed by a human looking at a blank window.
"""

import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_login_screen_qml_loads_without_errors(qapp):
    from unittest.mock import MagicMock

    from PySide6.QtQuickWidgets import QQuickWidget

    from app.ui.login_window import LoginWindow

    window = LoginWindow(MagicMock())
    try:
        assert window._quick_widget.status() != QQuickWidget.Status.Error, window._quick_widget.errors()
        assert window._quick_widget.rootObject() is not None
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


def test_login_screen_loads_against_a_genuinely_fresh_first_launch_database(qapp, monkeypatch, tmp_path):
    """Regression guard for the first-launch investigation recorded in
    PROJECT_CONTEXT.md: a "CRITICAL - hangs forever, no window ever
    appears" bug was reported after pointing an empty
    %LOCALAPPDATA%\\PetrolPumpERP at a fresh exe. That turned out to be a
    misdiagnosis - the investigation stopped at CPU/log activity going
    quiet and never checked whether a window had actually rendered; a
    real, correctly-titled, responsive window does render, confirmed by
    watching the actual packaged exe on a real desktop.

    Nothing in the suite covered this exact combination before: every
    other login test either passes a mocked AuthService (test_login_
    screen_qml_loads_without_errors above, no real database involved at
    all) or builds its schema with Base.metadata.create_all
    (test_login_bridge.py), skipping Alembic entirely. This test runs
    the real init_db() migration path against a database file that does
    not exist yet - the exact condition the bug report was about - then
    seeds it and constructs LoginWindow against a real AuthService, so a
    future regression in that combination (a migration that only breaks
    on a truly empty schema, or seed data the QML screen ends up
    depending on) would be caught here instead of only on a customer's
    first launch.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from PySide6.QtQuickWidgets import QQuickWidget

    from app.database.connection import init_db
    from app.database.seed import seed_initial_data
    from app.repositories.audit_log_repository import AuditLogRepository
    from app.repositories.user_repository import UserRepository
    from app.repositories.user_session_repository import UserSessionRepository
    from app.services.auth_service import AuthService
    from app.ui.login_window import LoginWindow

    sqlite_path = str(tmp_path / "petrol_pump.db")
    assert not os.path.exists(sqlite_path)  # the whole point: genuinely empty, nothing pre-created

    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.connection.DB_PATH", sqlite_path)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    init_db()  # real Alembic migrations, baseline schema included, against a file that doesn't exist yet
    seed_initial_data()

    session = session_factory()
    try:
        auth_service = AuthService(
            UserRepository(session),
            AuditLogRepository(session),
            UserSessionRepository(session),
        )

        window = LoginWindow(auth_service)
        try:
            assert window._quick_widget.status() != QQuickWidget.Status.Error, window._quick_widget.errors()
            assert window._quick_widget.rootObject() is not None
        finally:
            window.close()
            window.deleteLater()
            qapp.processEvents()
    finally:
        session.close()
