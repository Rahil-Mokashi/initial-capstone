import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, WeakPasswordError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService
from app.services.user_service import UserService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_user.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
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
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def shift_supervisor_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.SHIFT_SUPERVISOR.value, "supervisor1").id


@pytest.fixture()
def attendant_role_id(db_session):
    seed_initial_data()
    return db_session.query(Role).filter_by(name=UserRole.ATTENDANT.value).first().id


@pytest.fixture()
def user_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return UserService(UserRepository(db_session), RoleRepository(db_session), audit_repo, auth_service)


def make_user_data(**overrides) -> UserCreate:
    defaults = dict(
        username="new.attendant",
        email="new.attendant@example.com",
        password="Strong@123",
        role_id=overrides.pop("role_id", None),
    )
    defaults.update(overrides)
    return UserCreate(**defaults)


def test_create_user(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    assert user.username == "new.attendant"
    assert user.role_id == attendant_role_id
    assert user.is_active is True
    assert user.is_locked is False


def test_create_user_records_audit_log(user_service, admin_id, attendant_role_id, db_session):
    user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "user_created" in events


def test_duplicate_username_raises_conflict(user_service, admin_id, attendant_role_id):
    user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(ConflictError):
        user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id, email="different@example.com"))


def test_duplicate_email_raises_conflict(user_service, admin_id, attendant_role_id):
    user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(ConflictError):
        user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id, username="different.user"))


def test_unknown_role_raises_not_found(user_service, admin_id):
    with pytest.raises(NotFoundError):
        user_service.create_user(admin_id, make_user_data(role_id="does-not-exist"))


def test_weak_password_rejected(user_service, admin_id, attendant_role_id):
    with pytest.raises(WeakPasswordError):
        user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id, password="weak"))


def test_invalid_username_rejected_by_schema():
    with pytest.raises(ValidationError):
        UserCreate(username="a", email="x@example.com", password="Strong@123", role_id="r1")


def test_invalid_email_rejected_by_schema():
    with pytest.raises(ValidationError):
        UserCreate(username="validname", email="not-an-email", password="Strong@123", role_id="r1")


def test_shift_supervisor_cannot_create_user(user_service, shift_supervisor_id, attendant_role_id):
    with pytest.raises(PermissionDeniedError):
        user_service.create_user(shift_supervisor_id, make_user_data(role_id=attendant_role_id))


def test_set_user_active_requires_reason(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(ValueError):
        user_service.set_user_active(admin_id, user.id, False, "")


def test_deactivate_and_reactivate_user(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    deactivated = user_service.set_user_active(admin_id, user.id, False, "No longer employed")
    assert deactivated.is_active is False

    reactivated = user_service.set_user_active(admin_id, user.id, True, "Rehired")
    assert reactivated.is_active is True


def test_unlock_user_requires_reason(user_service, admin_id, attendant_role_id, db_session):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    user.is_locked = True
    db_session.commit()
    with pytest.raises(ValueError):
        user_service.unlock_user(admin_id, user.id, "")


def test_unlock_user_clears_lock_and_failed_attempts(user_service, admin_id, attendant_role_id, db_session):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    user.is_locked = True
    user.failed_attempts = 5
    db_session.commit()

    unlocked = user_service.unlock_user(admin_id, user.id, "Confirmed identity, resetting lock")
    assert unlocked.is_locked is False
    assert unlocked.failed_attempts == 0


def test_unlock_non_locked_user_raises_conflict(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(ConflictError):
        user_service.unlock_user(admin_id, user.id, "Just checking")


def test_change_user_role(user_service, admin_id, attendant_role_id, db_session):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    supervisor_role = db_session.query(Role).filter_by(name=UserRole.SHIFT_SUPERVISOR.value).first()

    updated = user_service.change_user_role(admin_id, user.id, supervisor_role.id, "Promoted to supervisor")
    assert updated.role_id == supervisor_role.id


def test_multiple_users_can_share_the_same_role(user_service, admin_id, attendant_role_id):
    user1 = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id, username="attendant.a", email="a@example.com"))
    user2 = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id, username="attendant.b", email="b@example.com"))
    assert user1.role_id == user2.role_id == attendant_role_id
    assert len(user_service.list_users(admin_id)) == 3  # admin + these two
