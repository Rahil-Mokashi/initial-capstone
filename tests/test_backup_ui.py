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


def test_backup_now_button_adds_a_row(qapp, qtbot, backup_service, admin_id, monkeypatch):
    # QMessageBox.information() is modal and blocks on a real display;
    # stub it out so this test can't hang waiting for a click that will
    # never come (same pattern as test_login_ui.py's session-expiry test).
    monkeypatch.setattr("app.ui.backup_window.QMessageBox.information", lambda *a, **k: None)

    from app.ui.backup_window import BackupWindow

    window = BackupWindow(backup_service, admin_id)
    assert window.table.rowCount() == 0

    # Backing up now runs on a worker thread (problemstatement.md #44:
    # never freeze the window), so the row appears when the task reports
    # back on the GUI thread rather than by the time this call returns.
    window._backup_now()
    qtbot.waitUntil(lambda: window.table.rowCount() == 1, timeout=10000)


def test_check_integrity_button_shows_a_passing_result(qapp, qtbot, backup_service, admin_id, monkeypatch):
    shown = {}
    monkeypatch.setattr("app.ui.backup_window.QMessageBox.information", lambda self, title, text: shown.update(title=title, text=text))

    from app.ui.backup_window import BackupWindow

    window = BackupWindow(backup_service, admin_id)
    # Also asynchronous now - PRAGMA integrity_check walks every page in
    # the file and is the slowest read the app performs.
    window._check_integrity()
    qtbot.waitUntil(lambda: "title" in shown, timeout=10000)

    assert shown["title"] == "Integrity check"
    assert "passed" in shown["text"]


def test_accountant_cannot_open_backup_window(qapp, backup_service, accountant_id):
    from app.core.exceptions import PermissionDeniedError
    from app.ui.backup_window import BackupWindow

    with pytest.raises(PermissionDeniedError):
        BackupWindow(backup_service, accountant_id)


# ---------------------------------------------------------------------
# Off-device backup: the button and the staleness nag
# ---------------------------------------------------------------------

def test_the_warning_banner_shows_when_no_offsite_copy_has_been_made(
    qapp, backup_service, admin_id
):
    """Every backup listed sits on the same drive as the database, so
    saying nothing would leave the operator believing they are protected."""
    from app.ui.backup_window import BackupWindow

    window = BackupWindow(backup_service, admin_id)
    assert window.offsite_warning.isHidden() is False
    assert "same drive" in window.offsite_warning.text()


def test_copying_without_selecting_a_backup_asks_for_a_selection(
    qapp, backup_service, admin_id, monkeypatch
):
    shown = {}
    monkeypatch.setattr("app.ui.backup_window.QMessageBox.information",
                        lambda self, title, text: shown.update(title=title, text=text))
    from app.ui.backup_window import BackupWindow

    window = BackupWindow(backup_service, admin_id)
    window._copy_offsite()
    assert "Select a backup" in shown["text"]


def test_a_fresh_offsite_copy_clears_the_warning(
    qapp, backup_service, admin_id, tmp_path, monkeypatch
):
    from app.ui.backup_window import BackupWindow
    from app.database.backup import copy_backup_to

    window = BackupWindow(backup_service, admin_id)
    usb = tmp_path / "usb"

    backup_path = backup_service.create_backup(admin_id).path
    copy_backup_to(backup_path, str(usb))
    window._last_offsite_dir = str(usb)
    window._refresh_offsite_warning()

    assert window.offsite_warning.isHidden() is True, window.offsite_warning.text()


def test_a_stale_offsite_copy_is_reported_with_its_age(
    qapp, backup_service, admin_id, tmp_path
):
    import os

    from app.database.backup import copy_backup_to
    from app.ui.backup_window import BackupWindow

    window = BackupWindow(backup_service, admin_id)
    usb = tmp_path / "usb"
    backup_path = backup_service.create_backup(admin_id).path
    destination = copy_backup_to(backup_path, str(usb))

    long_ago = os.path.getmtime(destination) - (30 * 86400)
    os.utime(destination, (long_ago, long_ago))

    window._last_offsite_dir = str(usb)
    window._refresh_offsite_warning()

    assert window.offsite_warning.isHidden() is False
    assert "30 days old" in window.offsite_warning.text()


def test_an_unreachable_destination_is_reported_not_crashed_on(
    qapp, backup_service, admin_id, tmp_path
):
    """An unplugged USB drive is the condition being reported."""
    from app.ui.backup_window import BackupWindow

    window = BackupWindow(backup_service, admin_id)
    window._last_offsite_dir = str(tmp_path / "unplugged")
    window._refresh_offsite_warning()

    assert window.offsite_warning.isHidden() is False
    assert "not reachable" in window.offsite_warning.text()


def test_the_offsite_folder_defaults_from_settings(
    qapp, backup_service, admin_id, tmp_path
):
    """Re-finding the USB drive on every copy is the friction that stops
    off-device backups actually happening, so Settings supplies the default."""
    from types import SimpleNamespace

    from app.ui.backup_window import BackupWindow

    usb = tmp_path / "usb"
    usb.mkdir()
    fake_settings = SimpleNamespace(
        get_company_profile=lambda: SimpleNamespace(offsite_backup_dir=str(usb)))

    window = BackupWindow(backup_service, admin_id, fake_settings)
    assert window._configured_offsite_dir() == str(usb)


def test_a_broken_settings_service_does_not_stop_backups_opening(
    qapp, backup_service, admin_id
):
    """Taking a backup matters more than defaulting a path, so a failure
    reading settings is swallowed rather than blocking the screen."""
    from types import SimpleNamespace

    from app.ui.backup_window import BackupWindow

    def explode():
        raise RuntimeError("settings unavailable")

    window = BackupWindow(backup_service, admin_id,
                          SimpleNamespace(get_company_profile=explode))
    assert window._configured_offsite_dir() is None
    assert window.offsite_warning.isHidden() is False
