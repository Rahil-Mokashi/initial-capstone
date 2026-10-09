# ADR: Migrate the UI to a JavaScript front end in an Electron shell

Status: accepted for the proof phase (Tanks screen only) - 2026-10-09
Reset point: tag `reset/pre-js-frontend-2026-10-09` (see `RESET_POINT.md`)

## Context

The back end (services, models, RBAC, audit log, Decimal money handling) is
correct and heavily tested (996 tests). Only the PySide6 UI is being
replaced, one screen at a time. The Qt app and its Inno Setup installer stay
working throughout. The product must stay **fully offline**.

How the Qt app wires things today (read before writing this ADR):

- `AppController` (`app/ui/main_window.py`) opens ONE `db_connection.SessionLocal()`,
  builds repositories on it, builds every service with the repos plus a shared
  `AuthService`, and hands services to windows.
- Every permission-checked service method takes `actor_user_id` as its first
  argument and is decorated with `@require_permission(...)`, which calls
  `self._auth_service.check_permission(user_id, permission)`, records a
  `permission_denied` audit row, and raises `PermissionDeniedError`.
- Login is `AuthService.authenticate(username, password)` ->
  `(ok, user_dict_with_session_token, error)`. The token is stored hashed in
  `user_sessions`; `validate_session(token)` returns the User or raises
  `SessionExpiredError`.

The API layer reuses exactly this: same repositories, same constructors, same
service methods, same permission names, `AuthService` as the only authority.

## Decisions

### Shell: Electron
Identical rendering on every PC (bundled Chromium, no dependence on the
machine's WebView2), the strongest printing control (silent print, printer
choice, print-to-PDF), mature native features, and no Rust toolchain.

- **Tauri - not the default.** Uses the OS WebView2, so rendering and print
  behaviour vary with the machine's WebView2 version, and printing control is
  thinner. It also needs a Rust toolchain in the build chain. Its smaller
  installer does not outweigh print control for a business that prints
  receipts and reports.
- **pywebview - not the default.** Also uses the OS web view (same variance),
  has the weakest printing story, and gives little control over process
  lifecycle, security hardening, and the request filter we need for the
  offline guarantee.

### Back end: existing Python behind FastAPI + uvicorn, as a sidecar
Packaged with PyInstaller as a SEPARATE executable that Electron's main
process spawns. Routers are thin: parse request, call the existing service,
serialize. **No business logic, rounding, or permission logic in routers.**
The API package lives in a new top-level `api/` directory and imports `app.*`;
`app/services`, `app/models`, `app/core` are not modified.

### Process lifecycle
Electron main: picks a free port, generates a random per-launch secret, starts
the sidecar on `127.0.0.1` with port and secret in environment variables
(`PPERP_API_PORT`, `PPERP_API_SECRET`), polls `/api/health`, then opens the
window. Single-instance lock. On quit: request graceful shutdown from the API
first (so SQLite WAL checkpoints cleanly), force-kill only after a timeout.
If the sidecar dies, show an error screen with a Restart action, never a
blank window.

### Front end
React + TypeScript (strict) + Vite; TanStack Query (server state); TanStack
Table (grids); React Router; react-hook-form + zod; Tailwind + Radix/shadcn-
style components; lucide icons. Tests: Vitest + Testing Library; Playwright
(Electron support) end-to-end.

### Offline
All assets bundled. Fonts via `@fontsource`, no Google Fonts, no CDN scripts,
no analytics, no auto-update calls, no outbound calls. Enforced three ways:
(1) strict CSP `default-src 'self'`; (2) Electron main-process
`session.webRequest` handler cancels anything not 127.0.0.1 or the app's own
files; (3) a build check that scans built output for external `http(s)://`
URLs, plus a Playwright test that fails on any outside request.

### Money and volume
The API sends Decimals as **strings** at the backend's scale (money 2 dp,
volume 3 dp, per `app/core/money.py`), never JSON numbers. The front end does
no float arithmetic on money; totals are computed server-side; the UI only
formats for display. Inputs are sent as strings too and parsed by the existing
Pydantic schemas into `Decimal`.

### Auth
`AuthService` is the only authority. `POST /api/auth/login` verifies through
it and returns its session token; every other endpoint requires
`Authorization: Bearer <token>` resolved by `AuthService.validate_session`,
AND the per-launch secret in `X-Launch-Secret` (so other local processes
cannot call the API). Bind `127.0.0.1` only (the server refuses anything
else), validate the `Host` header, no wildcard CORS, strict CSP.

### Electron hardening
`contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, no remote
module, no `<webview>`. Preload exposes a minimal typed API via `contextBridge`
(API base URL, launch secret, print helpers) and nothing else. New windows are
denied; navigation away from the app origin is blocked.

### Errors
`PermissionDeniedError` -> 403 `permission_denied`; validation -> 422
`validation_error`; `NotFoundError` -> 404 `not_found`; `ConflictError` ->
409 `conflict`; `SessionExpiredError` / bad token -> 401; failed login -> 401
`invalid_credentials`; `ValueError` from a service rule -> 422
`rule_violation`; anything else -> 500 `internal_error` with the generic
message and the traceback logged.

### Deferred (out of scope this session)
PIN sign-in, Windows Hello, screen lock, self-service reset, locale toggle,
Caps Lock warning, lockout countdown, code signing, auto-update.

## Judgment calls (also in JS_MIGRATION_LOG.md)

1. **DB session lifecycle.** Qt shares one long-lived session across the whole
   UI thread. A threaded HTTP server must not share one SQLAlchemy session, so
   the API opens one `SessionLocal()` per request and builds the needed
   services on it using the *same* repository classes and constructor
   arguments as `AppController`. Only the lifetime differs.
2. **`describe_unexpected_error`** lives in `app/ui/qt_utils.py`, which imports
   PySide6; importing it would drag Qt into the sidecar. The API has an
   equivalent (same logging, same message text). Moving the function into
   `app/core` is a recommended follow-up, not done here.
3. **Same database as the Qt build.** A frozen sidecar resolves the DB with the
   same rule as the Qt exe (`%LOCALAPPDATA%\PetrolPumpERP\petrol_pump.db`) unless
   `PETROL_PUMP_DB_PATH` is set. During migration both UIs can therefore work
   on the same data, which is the point of a staged migration.
