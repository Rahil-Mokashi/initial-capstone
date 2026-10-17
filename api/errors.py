"""One error envelope for every failure: {"error": {code, message, details}}.

Codes are stable strings the front end can switch on; messages are for
people. Mapping follows docs/adr-js-frontend.md.
"""

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    SessionExpiredError,
    WeakPasswordError,
)
from app.core.logging import logger
from app.services.credit_control_service import CreditLimitExceeded
from app.services.entry_workflow_service import LockBlockedByChecks

# Same text as app/ui/qt_utils.GENERIC_ERROR_MESSAGE. Duplicated on purpose:
# that module imports PySide6, which must not be dragged into the sidecar.
GENERIC_ERROR_MESSAGE = (
    "Something went wrong. Please try again, and contact your administrator if this keeps happening."
)


class ApiError(Exception):
    """Raised by api/ code itself (never by services) for protocol-level failures."""

    def __init__(self, status: int, code: str, message: str, details: Optional[dict] = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def envelope(status: int, code: str, message: str, details: Optional[Any] = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def describe_unexpected_error(exc: Exception) -> str:
    """Log the traceback, return the safe generic message (see qt_utils)."""
    logger.error("Unexpected error in API request: %s", exc, exc_info=exc)
    return GENERIC_ERROR_MESSAGE


def _field_errors(errors) -> list[dict]:
    out = []
    for err in errors:
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        out.append({"field": ".".join(loc), "message": str(err.get("msg", "")).removeprefix("Value error, ")})
    return out


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return envelope(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(PermissionDeniedError)
    async def _denied(_: Request, exc: PermissionDeniedError):
        return envelope(
            403, "permission_denied", "You don't have permission to do that.", {"permission": exc.permission}
        )

    @app.exception_handler(SessionExpiredError)
    async def _expired(_: Request, exc: SessionExpiredError):
        return envelope(401, "session_expired", "Your session has ended. Please sign in again.")

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError):
        return envelope(404, "not_found", str(exc))

    @app.exception_handler(CreditLimitExceeded)
    async def _credit_limit(_: Request, exc: CreditLimitExceeded):
        return envelope(409, "credit_limit_exceeded", str(exc), exc.details)

    @app.exception_handler(LockBlockedByChecks)
    async def _lock_blocked(_: Request, exc: LockBlockedByChecks):
        return envelope(409, "lock_blocked_by_checks", str(exc), exc.details)

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError):
        return envelope(409, "conflict", str(exc))

    @app.exception_handler(WeakPasswordError)
    async def _weak(_: Request, exc: WeakPasswordError):
        return envelope(422, "weak_password", str(exc))

    @app.exception_handler(AuthenticationError)
    async def _auth(_: Request, exc: AuthenticationError):
        return envelope(401, "authentication_failed", str(exc))

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return envelope(400, "app_error", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError):
        return envelope(422, "validation_error", "Some fields are not valid.", {"fields": _field_errors(exc.errors())})

    @app.exception_handler(ValidationError)
    async def _schema_validation(_: Request, exc: ValidationError):
        # Raised by the existing app/schemas models inside a service call.
        return envelope(422, "validation_error", "Some fields are not valid.", {"fields": _field_errors(exc.errors())})

    @app.exception_handler(ValueError)
    async def _rule(_: Request, exc: ValueError):
        # Services raise ValueError for rule violations (e.g. "A reason is required...").
        return envelope(422, "rule_violation", str(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        return envelope(500, "internal_error", describe_unexpected_error(exc))
