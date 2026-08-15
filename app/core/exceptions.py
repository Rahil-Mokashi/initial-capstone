"""Application-level exceptions for authentication and authorization."""


class AppError(Exception):
    """Base class for application errors."""


class AuthenticationError(AppError):
    """Raised when a login attempt fails for any reason."""


class AccountLockedError(AuthenticationError):
    """Raised when a login attempt is made against a locked account."""


class SessionExpiredError(AppError):
    """Raised when a session token is missing, expired, or invalidated."""


class PermissionDeniedError(AppError):
    """Raised when an authenticated user lacks a required permission."""

    def __init__(self, permission: str):
        self.permission = permission
        super().__init__(f"Permission denied: {permission}")


class WeakPasswordError(AppError):
    """Raised when a password does not meet the configured password policy."""
