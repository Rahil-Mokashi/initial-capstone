"""Runs the checks after data is saved ("checks run automatically when the relevant data is saved").

After any successful write (POST/PUT/PATCH/DELETE) the verdicts for the affected days are recomputed.
The work is handed to api.check_worker (background, merged bursts), so the save returns at once; the
verdicts themselves are append-only and audit-logged by CheckService.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from api.check_worker import request_run

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
        if scheme.lower() == "bearer" and token.strip():
            request_run(request.app, token.strip())
