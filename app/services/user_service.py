"""
User management service layer (problemstatement.md #6, #39).

Lets an admin create login accounts for any of the six business roles —
multiple users can share a role, matching how a real pump has several
attendants, possibly several accountants, etc. Accounts are never
deleted: deactivate/lock/unlock instead, all audit-logged, matching the
project's rule against destroying historical/security data.
"""

from typing import List

from app.core.constants import Permission
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, WeakPasswordError
from app.core.permissions import require_permission
from app.core.security import hash_password, validate_password_strength, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


class UserService:
    def __init__(self, user_repo, role_repo, audit_repo, auth_service):
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    @require_permission(Permission.USER_MANAGE.value)
    def create_user(self, actor_user_id: str, data: UserCreate) -> User:
        if self._user_repo.get_by_username(data.username):
            raise ConflictError(f"Username {data.username!r} is already taken")
        if self._user_repo.get_by_email(data.email):
            raise ConflictError(f"Email {data.email!r} is already registered")

        role = self._role_repo.get_by_id(data.role_id)
        if not role:
            raise NotFoundError(f"Role not found: {data.role_id}")

        password_errors = validate_password_strength(data.password)
        if password_errors:
            raise WeakPasswordError("; ".join(password_errors))

        user = User(
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            role_id=data.role_id,
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            # An admin-assigned password is a temporary one from the
            # account holder's point of view - force them to set their
            # own on first login rather than staying on it indefinitely.
            must_change_password=True,
        )
        user = self._user_repo.add(user)
        self._audit_repo.record(
            event_type="user_created",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=f"Created user {data.username} with role {role.name}",
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def list_users(self, actor_user_id: str) -> List[User]:
        return self._user_repo.list_all()

    @require_permission(Permission.USER_MANAGE.value)
    def set_user_active(self, actor_user_id: str, user_id: str, is_active: bool, reason: str) -> User:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to activate/deactivate a user")

        user = self._get_user_or_raise(user_id)
        old_value = "active" if user.is_active else "inactive"
        user.is_active = is_active
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_status_changed",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
            old_value=old_value,
            new_value="active" if is_active else "inactive",
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def unlock_user(self, actor_user_id: str, user_id: str, reason: str) -> User:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to unlock a user")

        user = self._get_user_or_raise(user_id)
        if not user.is_locked:
            raise ConflictError("This user is not locked")

        user.is_locked = False
        user.failed_attempts = 0
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_unlocked",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def change_user_role(self, actor_user_id: str, user_id: str, role_id: str, reason: str) -> User:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to change a user's role")

        user = self._get_user_or_raise(user_id)
        role = self._role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(f"Role not found: {role_id}")

        old_role_name = user.role.name if user.role else None
        user.role_id = role_id
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_role_changed",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
            old_value=old_role_name,
            new_value=role.name,
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def reset_password(self, actor_user_id: str, user_id: str, new_password: str, reason: str) -> User:
        """Admin-initiated reset, e.g. because a user forgot their
        password and is locked out with no self-service recovery path.
        Sets must_change_password so the temporary password an admin
        just typed doesn't become permanent by default."""
        if not reason or not reason.strip():
            raise ValueError("A reason is required to reset a user's password")

        password_errors = validate_password_strength(new_password)
        if password_errors:
            raise WeakPasswordError("; ".join(password_errors))

        user = self._get_user_or_raise(user_id)
        user.password_hash = hash_password(new_password)
        user.must_change_password = True
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_password_reset",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
        )
        return user

    def change_own_password(self, actor_user_id: str, current_password: str, new_password: str) -> User:
        """Self-service password change - any authenticated user may
        change their own password, no USER_MANAGE permission required.
        Used both for the forced first-login rotation and for a
        voluntary later change."""
        user = self._get_user_or_raise(actor_user_id)
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect")

        password_errors = validate_password_strength(new_password)
        if password_errors:
            raise WeakPasswordError("; ".join(password_errors))

        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_password_changed",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description="Self-service password change",
        )
        return user

    def _get_user_or_raise(self, user_id: str) -> User:
        user = self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")
        return user
