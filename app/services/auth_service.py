"""
Authentication service layer.

Handles login, logout, session validation, and permission checks. Every
authentication event (success, failure, lockout, logout, session expiry) is
written to the audit trail per problemstatement.md #40.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from app.core.constants import DEFAULT_SESSION_TIMEOUT_HOURS, LOCKOUT_DURATION_MINUTES, MAX_FAILED_LOGIN_ATTEMPTS
from app.core.exceptions import SessionExpiredError
from app.core.security import generate_token, verify_password


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; treat naive values as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class AuthService:
    """Service for authentication and authorization operations."""

    def __init__(
        self,
        user_repo,
        audit_repo,
        session_repo,
        session_timeout_hours: int = DEFAULT_SESSION_TIMEOUT_HOURS,
    ):
        self._user_repo = user_repo
        self._audit_repo = audit_repo
        self._session_repo = session_repo
        self._session_timeout = timedelta(hours=session_timeout_hours)

    def authenticate(
        self, username: str, password: str, device_info: Optional[str] = None
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """Authenticate user credentials.

        Returns: (success, user_data (including a session_token on success), error_message)
        """
        user = self._user_repo.get_by_username(username)
        if not user:
            self._audit_repo.record(
                event_type="login_failed",
                description=f"Unknown username: {username}",
                device_info=device_info,
            )
            # Deliberately generic: do not reveal whether the username exists.
            return False, None, "Invalid username or password"

        if user.is_locked and self._lockout_has_expired(user):
            # The lockout served its purpose and timed out. Clearing it here
            # rather than requiring an administrator is deliberate: a
            # permanent lock on a forecourt PC with no admin on the night
            # shift turns a security control into an availability outage,
            # and staff respond by sharing one never-locked login.
            self._clear_lockout(user)

        if user.is_locked:
            self._audit_repo.record(
                event_type="login_blocked",
                actor_id=user.id,
                description="Login attempted on locked account",
                device_info=device_info,
            )
            return False, None, (
                f"Account is locked due to failed attempts. "
                f"Try again in {LOCKOUT_DURATION_MINUTES} minutes, or ask an administrator to unlock it."
            )

        if not user.is_active:
            self._audit_repo.record(
                event_type="login_blocked",
                actor_id=user.id,
                description="Login attempted on deactivated account",
                device_info=device_info,
            )
            return False, None, "Account is deactivated"

        if not verify_password(password, user.password_hash):
            self._record_failed_login(user, device_info)
            return False, None, "Invalid username or password"

        self._record_successful_login(user)
        token = generate_token()
        expires_at = datetime.now(timezone.utc) + self._session_timeout
        self._session_repo.create(user.id, token, expires_at, device_info)
        self._audit_repo.record(event_type="login_success", actor_id=user.id, device_info=device_info)

        response = self._build_user_response(user)
        response["session_token"] = token
        response["expires_at"] = expires_at.isoformat()
        return True, response, None

    def _lockout_has_expired(self, user) -> bool:
        """True when an automatic lockout is old enough to lift itself.

        A lock with no locked_at was applied by an administrator (or
        predates this column), and must be cleared deliberately rather
        than timing out.
        """
        if user.locked_at is None:
            return False
        locked_at = _as_aware_utc(user.locked_at)
        return datetime.now(timezone.utc) - locked_at >= timedelta(minutes=LOCKOUT_DURATION_MINUTES)

    def _clear_lockout(self, user) -> None:
        user.is_locked = False
        user.locked_at = None
        user.failed_attempts = 0
        self._user_repo.update(user)
        self._audit_repo.record(
            event_type="login_lockout_expired",
            actor_id=user.id,
            description=f"Automatic lockout expired after {LOCKOUT_DURATION_MINUTES} minutes",
        )

    def _record_failed_login(self, user, device_info: Optional[str] = None) -> None:
        """Record a failed login attempt and lock the account after too many."""
        user.failed_attempts += 1
        locked = user.failed_attempts >= MAX_FAILED_LOGIN_ATTEMPTS
        if locked:
            user.is_locked = True
            # Stamped so the lockout can expire on its own.
            user.locked_at = datetime.now(timezone.utc)
        self._user_repo.update(user)
        self._audit_repo.record(
            event_type="login_locked" if locked else "login_failed",
            actor_id=user.id,
            description=f"Failed login attempt {user.failed_attempts}",
            device_info=device_info,
        )

    def _record_successful_login(self, user) -> None:
        """Reset failed-attempt counters and stamp last login time."""
        user.failed_attempts = 0
        user.is_locked = False
        user.locked_at = None
        user.last_login = datetime.now(timezone.utc)
        self._user_repo.update(user)

    def _build_user_response(self, user) -> dict:
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role.name if user.role else None,
            "permissions": sorted(p.name for p in user.role.permissions) if user.role else [],
            "must_change_password": user.must_change_password,
        }

    def validate_session(self, token: str):
        """Return the active User for a session token.

        Raises SessionExpiredError if the token is unknown, invalidated, or
        past its expiry (auto logout).
        """
        session_entry = self._session_repo.get_by_token(token)
        if not session_entry:
            raise SessionExpiredError("Session not found or already ended")

        if _as_aware_utc(session_entry.expires_at) < datetime.now(timezone.utc):
            self._session_repo.invalidate(session_entry)
            self._audit_repo.record(event_type="session_expired", actor_id=session_entry.user_id)
            raise SessionExpiredError("Session expired")

        self._session_repo.touch(session_entry)
        return self._user_repo.get_by_id(session_entry.user_id)

    def logout(self, token: str) -> bool:
        """Invalidate a session token. Returns False if it was already inactive."""
        session_entry = self._session_repo.get_by_token(token)
        if not session_entry:
            return False
        self._session_repo.invalidate(session_entry)
        self._audit_repo.record(event_type="logout", actor_id=session_entry.user_id)
        return True

    def check_permission(self, user_id: str, permission_name: str) -> bool:
        """Check whether a user's role grants a specific permission."""
        user = self._user_repo.get_by_id(user_id)
        if not user or not user.role:
            return False
        return any(p.name == permission_name for p in user.role.permissions)
