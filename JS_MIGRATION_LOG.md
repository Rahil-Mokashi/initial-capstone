# JS Migration Log

Running log of the Qt -> Electron/React migration (proof screen: Tanks).
Branch `feature/js-frontend`. Never pushed.

## Phase 0 - reset point (2026-10-09)
- Tree clean on `feature/login-screen-enhancements` @ `652c589`.
- Baseline full suite: **996 passed** (brief said 993; the suite grew). Took 5m20s, not ~23 min; no hang this run.
- Tag, bundle (verified okay), DB and exe copies, branch, `RESET_POINT.md`: done. See that file.
- Not touched: `%LOCALAPPDATA%\PetrolPumpERP\` (installed app's DB, may be real data).
- Commit style follows git log (`docs:`, `feat:`...). No attribution trailers on commits (owner's preference for this repo).

## Phase 1 - ADR
- `docs/adr-js-frontend.md` written. Judgment calls recorded there (per-request DB session,
  `describe_unexpected_error` equivalent without Qt, shared DB with the Qt build).

## Phase 2 - API layer
- Dependencies: fastapi 0.143.0, uvicorn 0.54.0 (+ starlette 1.7.0, anyio, h11, click, idna, annotated-doc,
  opentelemetry-api) added to requirements.txt, pyproject.toml and the HASH-PINNED requirements.lock
  (hashes fetched from PyPI; `pip install --dry-run --require-hashes -r requirements.lock` passes).
  The lock's `typing_extensions` moved 4.15.0 -> 4.16.0 because fastapi's closure pulled it in (global env).
  The installed fastapi was 0.104.1 / starlette 0.27, which is incompatible with the installed httpx 0.28
  test client, hence the upgrade. Starlette's TestClient prints a deprecation warning about httpx
  (it prefers httpx2); harmless today, watch on upgrades.
- Package `api/`: app factory, launch-secret dependency, per-request DB session, current-user
  dependency (AuthService.validate_session), error envelope, schemas, auth + tanks routers,
  health + graceful shutdown, `main.py` sidecar entry (loopback-only, WAL checkpoint on exit),
  `export_openapi.py` for type generation.
- Routes call the SAME TankService/EmployeeService/AuthService/UserService methods as the Qt Tanks window;
  no `*_as_related_action`. Permission checks stay in the services.
- Judgment calls:
  * Per-request Session instead of Qt's single long-lived one (thread safety); same repos/constructors.
  * `describe_unexpected_error` re-implemented in api/errors.py (Qt version imports PySide6).
  * Request decimals must be JSON STRINGS with <= 12 digits / <= 3 places (the Numeric(12,3) column). Anything
    finer is rejected with 422 instead of being silently rounded by the database.
  * `/api/lookups/fuels` (Qt reads FuelRepository.list_active() unchecked, but only shows the dialog to
    INVENTORY_MANAGE users) is gated on INVENTORY_MANAGE through AuthService.check_permission + audit of denial.
  * Forced password change: Qt enforces it only in the UI. The API additionally returns 403
    `password_change_required` for everything except /auth/* until the password is changed (the seeded
    admin has the flag set, so login alone would otherwise be a bypass of the Qt behaviour).
  * Only the Qt screen's three transaction types (receipt/issue/adjustment) are accepted.
  * `fill_percent`/`is_low` are computed server-side (same clamp as app/ui/widgets.stock_percent and the
    DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT constant) so the browser does no arithmetic on stock.
  * Session user deactivated mid-session: Qt does not re-check `is_active` on validate_session; the API
    does (401). Stricter than Qt, not looser.
- Tests: tests/api (107): every endpoint x {401 no token, 401 bad token, 403 missing/wrong secret};
  per-endpoint success, 403 (role without the permission), 422, 404/409 rules; AuditLog row asserted for
  every state-changing call and `verify_chain()` after; decimals-as-strings contract; loopback-only bind;
  Host header; CSP; no CORS; no docs endpoints; 500 mapping.
- Full suite after phase: **1103 passed** (996 baseline + 107 API), 8m08s, no hang.
- Observation (not changed): the Qt `TankService` has no way to list ISSUE transactions made by sales with
  their sale link; unrelated to this phase.

## Deferred (per brief)
PIN sign-in, Windows Hello, screen lock, self-service reset, locale toggle, Caps Lock warning,
lockout countdown, code signing, auto-update.

## NEEDS HUMAN REVIEW
(none yet)
