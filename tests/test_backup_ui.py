import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_backup_ui.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session, sqlite_path
    session.close()


def make_user(db_session, role_name: str, username: str) -> User:
    role = db_session.query(Role).filter_by(name=role_name).first()
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_id(db_session):
    session, _ = db_session
    seed_initial_data()
    return session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def accountant_id(db_session):
    session, _ = db_session
    seed_initial_data()
    return make_user(session, UserRole.ACCOUNTANT.value, "accountant1").id


@pytest.fixture()
def backup_service(db_session):
    session, sqlite_path = db_session
    audit_repo = AuditLogRepository(session)
    auth_service = AuthService(UserRepository(session), audit_repo, UserSessionRepository(session))
    return BackupService(sqlite_path, audit_repo, auth_service)


def test_window_shows_existing_backups(qapp, backup_service, admin_id):
    from app.ui.backup_window import BackupWindow

    backup_service.create_backup(admin_id)
    window = BackupWindow(backup_service, admin_id)
    assert window.table.rowCount() == 1


def test_backup_now_button_adds_a_row(qapp, backup_service, admin_id, monkeypatch):
    # QMessageBox.information() is modal and blocks on a real display;
    # stub it out so this test can't hang waiting for a click that will
    # never come (same pattern as test_login_ui.py's session-expiry test).
    monkeypatch.setattr("app.ui.backup_window.QMessageBox.information", lambda *a, **k: None)

    from app.ui.backup_window import BackupWindow

    window = BackupWindow(backup_service, admin_id)
    assert window.table.rowCount() == 0

    window._backup_now()
    assert window.table.rowCount() == 1


def test_check_integrity_button_shows_a_passing_result(qapp, backup_service, admin_id, monkeypatch):
    shown = {}
    monkeypatch.setattr("app.ui.backup_window.QMessageBox.information", lambda self, title, text: shown.update(title=title, text=text))

    from app.ui.backup_window import BackupWindow

    window = BackupWindow(backup_service, admin_id)
    window._check_integrity()

    assert shown["title"] == "Integrity check"
    assert "passed" in shown["text"]


def test_accountant_cannot_open_backup_window(qapp, backup_service, accountant_id):
    from app.core.exceptions import PermissionDeniedError
    from app.ui.backup_window import BackupWindow

    with pytest.raises(PermissionDeniedError):
        BackupWindow(backup_service, accountant_id)
