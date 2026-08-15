from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import MAX_FAILED_LOGIN_ATTEMPTS, Permission as PermissionName, UserRole
from app.core.exceptions import PermissionDeniedError, SessionExpiredError
from app.core.permissions import require_permission
from app.core.security import hash_password, validate_password_strength
from app.database.base import Base
from app.database.seed import DEFAULT_ADMIN_PASSWORD, seed_initial_data
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_auth.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    # seed_initial_data() opens its own session via db_package.connection.SessionLocal,
    # so it must point at the same test engine/session factory.
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def auth_service(db_session):
    seed_initial_data()
    user_repo = UserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    session_repo = UserSessionRepository(db_session)
    return AuthService(user_repo, audit_repo, session_repo, session_timeout_hours=8)


def make_attendant(db_session) -> User:
    role = db_session.query(Role).filter_by(name=UserRole.ATTENDANT.value).first()
    user = User(
        username="attendant1",
        email="attendant1@example.com",
        password_hash=hash_password("Attendant@123"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_seed_creates_all_roles_and_permissions(db_session):
    seed_initial_data()
    role_names = {r.name for r in db_session.query(Role).all()}
    assert role_names == {r.value for r in UserRole}


def test_seed_is_idempotent(db_session):
    seed_initial_data()
    seed_initial_data()
    assert db_session.query(User).filter_by(username="admin").count() == 1
    assert db_session.query(Role).filter_by(name=UserRole.ADMIN.value).count() == 1


def test_seed_creates_default_fuel_types(db_session):
    from app.core.constants import DEFAULT_FUEL_TYPES
    from app.models.fuel import Fuel

    seed_initial_data()
    fuel_types = {f.fuel_type for f in db_session.query(Fuel).all()}
    assert fuel_types == set(DEFAULT_FUEL_TYPES)


def test_seed_fuel_types_idempotent(db_session):
    from app.models.fuel import Fuel

    seed_initial_data()
    seed_initial_data()
    assert db_session.query(Fuel).count() == len(db_session.query(Fuel).all())
    assert db_session.query(Fuel).filter_by(fuel_type="Petrol").count() == 1


def test_authenticate_success(auth_service):
    success, data, error = auth_service.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
    assert success is True
    assert error is None
    assert data["role"] == UserRole.ADMIN.value
    assert "session_token" in data
    assert PermissionName.USER_MANAGE.value in data["permissions"]


def test_authenticate_wrong_password_is_generic_and_counts_attempt(auth_service, db_session):
    success, data, error = auth_service.authenticate("admin", "wrong-password")
    assert success is False
    assert data is None
    assert error == "Invalid username or password"

    admin = db_session.query(User).filter_by(username="admin").first()
    assert admin.failed_attempts == 1


def test_authenticate_unknown_username_gives_same_generic_error(auth_service):
    success, data, error = auth_service.authenticate("nobody", "whatever")
    assert success is False
    assert error == "Invalid username or password"


def test_account_locks_after_max_failed_attempts(auth_service, db_session):
    for _ in range(MAX_FAILED_LOGIN_ATTEMPTS):
        auth_service.authenticate("admin", "wrong-password")

    admin = db_session.query(User).filter_by(username="admin").first()
    assert admin.is_locked is True

    success, data, error = auth_service.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
    assert success is False
    assert error == "Account is locked due to failed attempts"


def test_check_permission_admin_has_full_access(auth_service, db_session):
    admin = db_session.query(User).filter_by(username="admin").first()
    assert auth_service.check_permission(admin.id, PermissionName.USER_MANAGE.value) is True


def test_check_permission_attendant_has_no_permissions(auth_service, db_session):
    attendant = make_attendant(db_session)
    assert auth_service.check_permission(attendant.id, PermissionName.USER_MANAGE.value) is False


def test_session_validate_and_logout(auth_service):
    success, data, _ = auth_service.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
    assert success is True
    token = data["session_token"]

    user = auth_service.validate_session(token)
    assert user.username == "admin"

    assert auth_service.logout(token) is True
    with pytest.raises(SessionExpiredError):
        auth_service.validate_session(token)


def test_session_auto_expires(auth_service, db_session):
    success, data, _ = auth_service.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
    token = data["session_token"]

    session_repo = UserSessionRepository(db_session)
    entry = session_repo.get_by_token(token)
    entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(SessionExpiredError):
        auth_service.validate_session(token)


def test_password_policy_rejects_weak_password():
    errors = validate_password_strength("weak")
    assert errors

    errors = validate_password_strength("Strong@123")
    assert errors == []


def test_audit_log_records_login_success_and_failure(auth_service, db_session):
    auth_service.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
    auth_service.authenticate("admin", "wrong-password")

    from app.models.audit_log import AuditLog

    event_types = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "login_success" in event_types
    assert "login_failed" in event_types


def test_require_permission_decorator_blocks_unauthorized(auth_service, db_session):
    class DummyService:
        def __init__(self, auth_service):
            self._auth_service = auth_service

        @require_permission(PermissionName.USER_MANAGE.value)
        def do_admin_thing(self, user_id):
            return "done"

    attendant = make_attendant(db_session)
    admin = db_session.query(User).filter_by(username="admin").first()
    dummy = DummyService(auth_service)

    assert dummy.do_admin_thing(admin.id) == "done"
    with pytest.raises(PermissionDeniedError):
        dummy.do_admin_thing(attendant.id)
