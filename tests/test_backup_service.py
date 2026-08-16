import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.exceptions import PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_backup_service.db")
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


def test_create_backup_returns_info_and_records_audit_log(backup_service, admin_id, db_session):
    session, _ = db_session
    info = backup_service.create_backup(admin_id)

    assert info.size_bytes > 0
    events = {log.event_type for log in session.query(AuditLog).all()}
    assert "backup_created" in events


def test_create_backup_denied_without_permission(backup_service, accountant_id):
    with pytest.raises(PermissionDeniedError):
        backup_service.create_backup(accountant_id)


def test_list_backups_denied_without_permission(backup_service, accountant_id):
    with pytest.raises(PermissionDeniedError):
        backup_service.list_backups(accountant_id)


def test_list_backups_reflects_created_backups(backup_service, admin_id):
    backup_service.create_backup(admin_id)
    backup_service.create_backup(admin_id)
    assert len(backup_service.list_backups(admin_id)) == 2


def test_restore_requires_reason(backup_service, admin_id):
    info = backup_service.create_backup(admin_id)
    with pytest.raises(ValueError):
        backup_service.restore_backup(admin_id, info.path, "")


def test_restore_denied_without_permission(backup_service, accountant_id, admin_id):
    info = backup_service.create_backup(admin_id)
    with pytest.raises(PermissionDeniedError):
        backup_service.restore_backup(accountant_id, info.path, "Testing restore")


def test_restore_records_audit_log(backup_service, admin_id, db_session):
    session, _ = db_session
    info = backup_service.create_backup(admin_id)

    backup_service.restore_backup(admin_id, info.path, "Recovering from a bad data entry")

    events = {log.event_type for log in session.query(AuditLog).all()}
    assert "database_restored" in events


def test_restore_takes_a_safety_backup_of_the_pre_restore_state(backup_service, admin_id):
    """restore_backup must back up the current (pre-restore) state first,
    so restoring to the wrong backup by mistake is itself recoverable."""
    info = backup_service.create_backup(admin_id)
    before_restore = len(backup_service.list_backups(admin_id))

    backup_service.restore_backup(admin_id, info.path, "Testing safety backup")

    after_restore = backup_service.list_backups(admin_id)
    assert len(after_restore) == before_restore + 1  # the restore's own pre_restore safety backup
    assert any("pre_restore" in b.filename for b in after_restore)


def test_restore_actually_overwrites_the_live_database(backup_service, admin_id, db_session):
    session, sqlite_path = db_session
    info = backup_service.create_backup(admin_id)

    # Mutate the live DB after the backup was taken.
    connection = sqlite3.connect(sqlite_path)
    connection.execute(
        "INSERT INTO fuels (id, fuel_type, rate_per_liter, is_active, created_at, updated_at, status, is_deleted) "
        "VALUES ('x', 'Test', 1.0, 1, datetime('now'), datetime('now'), 'active', 0)"
    )
    connection.commit()
    connection.close()

    backup_service.restore_backup(admin_id, info.path, "Undo the test fuel row")

    connection = sqlite3.connect(sqlite_path)
    count = connection.execute("SELECT COUNT(*) FROM fuels WHERE id='x'").fetchone()[0]
    connection.close()
    assert count == 0
