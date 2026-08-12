"""
Authentication service layer
Handles user login, logout, and session management
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple
import secrets
import hashlib


class AuthService:
    """Service for authentication and authorization operations"""

    def __init__(self, user_repo, role_repo, permission_repo):
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._permission_repo = permission_repo
        self._session_timeout = timedelta(hours=8)

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Authenticate user credentials
        Returns: (success, user_data, error_message)
        """
        user = self._user_repo.get_by_username(username)
        if not user:
            return False, None, "Invalid username"

        if not user.is_active:
            return False, None, "Account is deactivated"

        if user.is_locked:
            return False, None, "Account is locked due to failed attempts"

        if not self._verify_password(password, user.password_hash):
            self._record_failed_login(user.id)
            return False, None, "Invalid password"

        self._record_successful_login(user.id)
        return True, self._build_user_response(user), None

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against stored hash"""
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        return secrets.compare_digest(pwd_hash, password_hash)

    def _record_failed_login(self, user_id: int) -> None:
        """Record failed login attempt"""
        user = self._user_repo.get_by_id(user_id)
        user.failed_attempts += 1
        if user.failed_attempts >= 5:
            user.is_locked = True
        self._user_repo.update(user)

    def _record_successful_login(self, user_id: int) -> None:
        """Record successful login"""
        user = self._user_repo.get_by_id(user_id)
        user.failed_attempts = 0
        user.is_locked = False
        user.last_login = datetime.utcnow()
        user.is_active = True
        self._user_repo.update(user)

    def _build_user_response(self, user) -> dict:
        """Build user response data"""
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role.name if user.role else None,
            "permissions": [p.name for p in user.role.permissions] if user.role and hasattr(user.role, 'permissions') else []
        }

    def check_permission(self, user_id: int, permission: str) -> bool:
        """Check if user has specific permission"""
        user = self._user_repo.get_by_id(user_id)
        if not user or not user.role:
            return False

        # Check role permissions
        for rp in user.role.role_permissions:
            if rp.permission.name == permission:
                return True
        return False

    def logout(self, user_id: int) -> bool:
        """Handle user logout"""
        # Clear session data, tokens, etc.
        return True