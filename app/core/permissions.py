"""Permission-checking decorator for service-layer methods.

There is no web framework/request context in this desktop app, so
permission checks are applied directly to service methods instead of
route decorators. Contract: the decorated method must belong to a class
with an `self._auth_service` (an AuthService instance) and must accept
the acting user's id as its first positional argument after `self`.
"""

from functools import wraps

from app.core.exceptions import PermissionDeniedError


def require_permission(permission_name: str):
    def decorator(func):
        @wraps(func)
        def wrapper(self, user_id, *args, **kwargs):
            if not self._auth_service.check_permission(user_id, permission_name):
                raise PermissionDeniedError(permission_name)
            return func(self, user_id, *args, **kwargs)

        return wrapper

    return decorator
