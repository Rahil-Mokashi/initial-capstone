import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    WeakPasswordError,
)
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


def test_create_user_forces_password_change_on_first_login(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    assert user.must_change_password is True


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


def test_reset_password_requires_reason(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(ValueError):
        user_service.reset_password(admin_id, user.id, "NewStrong@123", "")


def test_reset_password_rejects_weak_password(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(WeakPasswordError):
        user_service.reset_password(admin_id, user.id, "weak", "User forgot their password")


def test_reset_password_forces_change_on_next_login(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    # A real self-service change would already have cleared this after
    # first login; force it False here to prove reset_password re-sets it.
    user.must_change_password = False

    updated = user_service.reset_password(admin_id, user.id, "NewStrong@123", "User forgot their password")
    assert updated.must_change_password is True


def test_reset_password_shift_supervisor_denied(user_service, shift_supervisor_id, attendant_role_id, admin_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(PermissionDeniedError):
        user_service.reset_password(shift_supervisor_id, user.id, "NewStrong@123", "Forgot password")


def test_change_own_password_requires_correct_current_password(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(AuthenticationError):
        user_service.change_own_password(user.id, "wrong-current-password", "NewStrong@123")


def test_change_own_password_rejects_weak_new_password(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(WeakPasswordError):
        user_service.change_own_password(user.id, "Strong@123", "weak")


def test_change_own_password_clears_must_change_password_flag(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    assert user.must_change_password is True

    updated = user_service.change_own_password(user.id, "Strong@123", "NewStrong@123")
    assert updated.must_change_password is False


def test_change_own_password_records_audit_log(user_service, admin_id, attendant_role_id, db_session):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    user_service.change_own_password(user.id, "Strong@123", "NewStrong@123")
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "user_password_changed" in events


def test_change_own_password_does_not_require_user_manage_permission(user_service, attendant_role_id, admin_id):
    """An attendant with no USER_MANAGE permission must still be able to
    change their own password - the whole point is that it's self-service."""
    attendant = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    updated = user_service.change_own_password(attendant.id, "Strong@123", "NewStrong@123")
    assert updated.must_change_password is False


# --- Quick-sign-in PIN -----------------------------------------------------


def test_set_own_pin_requires_correct_current_password(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(AuthenticationError):
        user_service.set_own_pin(user.id, "wrong-current-password", "482913")


def test_set_own_pin_rejects_wrong_length(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(WeakPasswordError):
        user_service.set_own_pin(user.id, "Strong@123", "1234")


def test_set_own_pin_rejects_repeated_digits(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(WeakPasswordError):
        user_service.set_own_pin(user.id, "Strong@123", "111111")


def test_set_own_pin_rejects_sequential_digits(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(WeakPasswordError):
        user_service.set_own_pin(user.id, "Strong@123", "123456")


def test_set_own_pin_succeeds_and_is_hashed_not_plaintext(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    updated = user_service.set_own_pin(user.id, "Strong@123", "482913")

    assert updated.pin_hash is not None
    assert updated.pin_hash != "482913"
    assert updated.pin_set_at is not None


def test_set_own_pin_records_audit_log(user_service, admin_id, attendant_role_id, db_session):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    user_service.set_own_pin(user.id, "Strong@123", "482913")
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "user_pin_set" in events


def test_authenticate_with_pin_succeeds_after_it_is_set(user_service, admin_id, attendant_role_id, db_session):
    from app.repositories.audit_log_repository import AuditLogRepository
    from app.repositories.user_repository import UserRepository
    from app.repositories.user_session_repository import UserSessionRepository
    from app.services.auth_service import AuthService

    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    user_service.set_own_pin(user.id, "Strong@123", "482913")

    auth_service = AuthService(
        UserRepository(db_session), AuditLogRepository(db_session), UserSessionRepository(db_session)
    )
    success, data, error = auth_service.authenticate_with_pin(user.username, "482913")
    assert success is True
    assert data["username"] == user.username
    assert "session_token" in data


def test_authenticate_with_pin_fails_generically_when_no_pin_is_set(user_service, admin_id, attendant_role_id, db_session):
    """An account with no PIN configured must fail with the exact same
    message a wrong PIN would - see AuthService.authenticate_with_pin's
    own docstring on why distinguishing the two would leak which
    accounts exist."""
    from app.repositories.audit_log_repository import AuditLogRepository
    from app.repositories.user_repository import UserRepository
    from app.repositories.user_session_repository import UserSessionRepository
    from app.services.auth_service import AuthService

    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))

    auth_service = AuthService(
        UserRepository(db_session), AuditLogRepository(db_session), UserSessionRepository(db_session)
    )
    success, data, error = auth_service.authenticate_with_pin(user.username, "482913")
    assert success is False
    assert error == "That username or PIN isn't correct. Please check and try again."


def test_wrong_pin_counts_toward_the_same_lockout_as_password(user_service, admin_id, attendant_role_id, db_session):
    from app.core.constants import MAX_FAILED_LOGIN_ATTEMPTS
    from app.repositories.audit_log_repository import AuditLogRepository
    from app.repositories.user_repository import UserRepository
    from app.repositories.user_session_repository import UserSessionRepository
    from app.services.auth_service import AuthService

    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    user_service.set_own_pin(user.id, "Strong@123", "482913")

    auth_service = AuthService(
        UserRepository(db_session), AuditLogRepository(db_session), UserSessionRepository(db_session)
    )
    for _ in range(MAX_FAILED_LOGIN_ATTEMPTS):
        auth_service.authenticate_with_pin(user.username, "000000")

    # Locked out of PASSWORD sign-in too, by the same counter - one
    # account, one lockout, not a separate guessing surface per credential.
    success, _data, error = auth_service.authenticate(user.username, "Strong@123")
    assert success is False
    assert "locked" in error


# --- Admin-generated password reset code -----------------------------------


def test_generate_password_reset_code_requires_reason(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(ValueError):
        user_service.generate_password_reset_code(admin_id, user.id, "")


def test_generate_password_reset_code_requires_user_manage_permission(user_service, shift_supervisor_id, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    with pytest.raises(PermissionDeniedError):
        user_service.generate_password_reset_code(shift_supervisor_id, user.id, "Forgot password, no admin on site")


def test_reset_password_with_code_succeeds_and_is_single_use(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    code = user_service.generate_password_reset_code(admin_id, user.id, "Forgot password, night shift")

    user_service.reset_password_with_code(user.username, code, "BrandNew@123")

    # The account can now sign in with the new password...
    updated = user_service._get_user_or_raise(user.id)
    assert verify_password_helper(updated.password_hash, "BrandNew@123")

    # ...and the same code cannot be reused a second time.
    with pytest.raises(AuthenticationError):
        user_service.reset_password_with_code(user.username, code, "AnotherNew@123")


def test_reset_password_with_code_rejects_expired_code(user_service, admin_id, attendant_role_id, db_session):
    from datetime import datetime, timedelta, timezone

    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    code = user_service.generate_password_reset_code(admin_id, user.id, "Forgot password")

    stored = user_service._get_user_or_raise(user.id)
    stored.password_reset_code_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(AuthenticationError):
        user_service.reset_password_with_code(user.username, code, "BrandNew@123")


def test_reset_password_with_code_rejects_wrong_code(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    user_service.generate_password_reset_code(admin_id, user.id, "Forgot password")

    with pytest.raises(AuthenticationError):
        user_service.reset_password_with_code(user.username, "00000000", "BrandNew@123")


def test_reset_password_with_code_rejects_unknown_username_with_the_same_message(user_service):
    try:
        user_service.reset_password_with_code("nobody-at-all", "12345678", "BrandNew@123")
        assert False, "expected AuthenticationError"
    except AuthenticationError as exc:
        assert str(exc) == "That reset code isn't valid or has expired. Please ask an administrator for a new one."


def test_reset_password_with_code_clears_must_change_password(user_service, admin_id, attendant_role_id):
    user = user_service.create_user(admin_id, make_user_data(role_id=attendant_role_id))
    assert user.must_change_password is True
    code = user_service.generate_password_reset_code(admin_id, user.id, "Forgot password")

    user_service.reset_password_with_code(user.username, code, "BrandNew@123")

    updated = user_service._get_user_or_raise(user.id)
    assert updated.must_change_password is False


def verify_password_helper(password_hash: str, plaintext: str) -> bool:
    from app.core.security import verify_password

    return verify_password(plaintext, password_hash)
