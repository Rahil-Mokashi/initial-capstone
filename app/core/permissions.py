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
                # Record before raising. A refused action is a security
                # event in its own right (problemstatement.md #43 lists
                # "Unauthorized action" as an alert), and this decorator is
                # the single chokepoint every permission check in the app
                # already passes through - so recording here covers all of
                # them at once and cannot be forgotten on a new service.
                #
                # getattr rather than a direct call: a handful of test
                # doubles stand in for AuthService with only
                # check_permission on them, and a denial must still deny
                # even when there is nowhere to record it.
                recorder = getattr(self._auth_service, "record_permission_denied", None)
                if recorder is not None:
                    recorder(user_id, permission_name)
                raise PermissionDeniedError(permission_name)
            return func(self, user_id, *args, **kwargs)

        return wrapper

    return decorator
