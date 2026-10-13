"""Runs the checks after data is saved ("checks run automatically when the relevant data is saved").

After any successful write (POST/PUT/PATCH/DELETE) the verdicts for the affected days are recomputed.
It can never break or slow-fail the user's request: errors are logged and swallowed, and the
verdicts themselves are append-only and audit-logged by CheckService.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from api.services import Services
from app.core.logging import logger

_SKIP = ("/api/checks", "/api/auth", "/api/system")


class RunChecksAfterWrites(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (
            request.method in ("POST", "PUT", "PATCH", "DELETE")
            and response.status_code < 400
            and path.startswith("/api")
            and not path.startswith(_SKIP)
            and not (path.startswith("/api/close-shift/") and path.endswith("/tally"))  # a preview saves nothing
        ):
            self._run(request)
        return response

    @staticmethod
    def _run(request: Request) -> None:
        scheme, _, token = (request.headers.get("authorization") or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return
        db = request.app.state.session_factory()
        try:
            services = Services(db, request.app.state.session_timeout_hours)
            user = services.auth.validate_session(token.strip())
            if user is None:
                return
            for day in services.days_to_check():
                services.run_all_checks(user.id, day)
        except Exception as exc:  # a verification problem must never break the save that triggered it
            logger.error("Automatic checks failed: %s", exc, exc_info=exc)
            db.rollback()
        finally:
            db.close()
