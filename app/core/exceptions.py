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


class NotFoundError(AppError):
    """Raised when a requested record does not exist (or is soft-deleted)."""


class ConflictError(AppError):
    """Raised when an operation would violate a uniqueness/business constraint."""


class DatabaseInitializationError(AppError):
    """Raised when the database cannot be created/seeded at application startup.

    Wraps the underlying SQLAlchemyError/OSError so callers (main.py, the
    UI launcher) can show a clear message instead of a raw traceback —
    problemstatement.md #43 requires a "Database error" notification and
    #44 requires the app to stay responsive/fail predictably.
    """
