"""App factory. Everything under /api needs the per-launch secret; everything
except /api/health, /api/auth/login needs a session token as well."""

from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from api.deps import require_launch_secret
from api.errors import install_error_handlers
from api.routers import attendance, auth, employees, fuel_prices, nozzles, procurement, sales, shifts, tanks, terminal, users

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# default-src 'self' as required. Two narrow additions the UI toolkit needs:
# inline style ATTRIBUTES (popover positioning) and data: images (icons).
# No inline <script>/<style> blocks, no remote origins of any kind.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
        return response


def create_app(
    launch_secret: str,
    session_factory: Optional[Callable] = None,
    session_timeout_hours: Optional[int] = None,
    web_dir: Optional[Path] = None,
    shutdown_callback: Optional[Callable[[], None]] = None,
) -> FastAPI:
    if not launch_secret:
        raise ValueError("launch_secret is required")

    if session_factory is None:
        from app.database import connection

        session_factory = connection.SessionLocal
    if session_timeout_hours is None:
        from app.core.config import settings

        session_timeout_hours = settings.session_timeout_hours

    # No interactive docs endpoints: the OpenAPI JSON is exported by a script for the type generator.
    app = FastAPI(title="Petrol Pump ERP local API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.launch_secret = launch_secret
    app.state.session_factory = session_factory
    app.state.session_timeout_hours = session_timeout_hours
    app.state.shutdown_callback = shutdown_callback

    # Added last = outermost: host check runs before anything else.
    app.add_middleware(SecurityHeaders)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    install_error_handlers(app)

    api = APIRouter(prefix="/api", dependencies=[Depends(require_launch_secret)])

    @api.get("/health")
    def health():
        return {"status": "ok"}

    @api.post("/system/shutdown", status_code=202)
    def shutdown(request: Request):
        """Graceful stop so SQLite checkpoints its WAL. Needs the launch secret only:
        Electron's main process calls this on quit, when nobody is signed in."""
        callback = request.app.state.shutdown_callback
        if callback is not None:
            callback()
        return {"status": "shutting_down"}

    api.include_router(auth.router)
    api.include_router(tanks.router)
    api.include_router(employees.router)
    api.include_router(fuel_prices.router)
    api.include_router(users.router)
    api.include_router(nozzles.router)
    api.include_router(procurement.router)
    api.include_router(shifts.router)
    api.include_router(attendance.router)
    api.include_router(sales.router)
    api.include_router(terminal.router)
    app.include_router(api)

    if web_dir is not None and Path(web_dir).is_dir():
        # The built UI is public code, served same-origin so no CORS is ever needed.
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app
