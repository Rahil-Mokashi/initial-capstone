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

## Deferred (per brief)
PIN sign-in, Windows Hello, screen lock, self-service reset, locale toggle, Caps Lock warning,
lockout countdown, code signing, auto-update.

## NEEDS HUMAN REVIEW
(none yet)
