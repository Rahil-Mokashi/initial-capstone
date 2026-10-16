# PILOT_LOG

Run started: 2026-10-16 12:36 (+05:30). Branch `feature/pilot-prep` from `feature/lan-multi-user` (a382280).
The run was paused by the developer between about 12:40 and 12:55 for a demo.

## Phase 0 - preflight (12:36)

- Working tree: only the developer's untracked `PILOT_READINESS_REPORT.md` (left alone). `PROMPT_PILOT.md` added to `.gitignore` (`run_prompt.ps1` and `private_samples/` were already there).
- Reset point: tag `reset/pre-pilot-2026-10-16`, verified bundle in the parent folder, recorded in `RESET_POINT.md`.
- Baseline (before any change):
  - Web Vitest: all passed (audit: 388).
  - Desktop Vitest: 46 passed.
  - Python: running on a clean worktree of the tag (result below when finished).
  - Playwright: result below.
