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

## CHECKPOINT - paused by the developer at 13:06 (nothing after this has been started)

Resume from: **Phase 1, step 2** (take checks off the save path). Phase 1 step 1 (benchmark) is written but only partly run.

Done so far (committed: reset point + log; benchmark scripts committed with this checkpoint):
- scripts/bench/generate_year.py (adapted from the audit's generator; `BENCH_NOZZLES_PER_DISPENSER` env, default 2 until Phase 2 lifts the cap) and scripts/bench/measure.py (works on a COPY of a generated DB; uses `api.check_worker.wait_idle(app, timeout)` once that module exists).
- Data was generated from a clean worktree of the reset tag (so it is "old code" data): `C:/Users/Asus/AppData/Local/Temp/claude/c--Users-Asus-Projects-PetrolPumpERP/debfa87f-7f7b-467e-88f6-8bfc46d00e7e/scratchpad/bench/y30.db` (done, 150 s) and `y365.db` (still generating in the background, about 75 min; done when `y365.meta.json` exists next to it).
- BEFORE at 30 days (machine was busy with the baseline pytest run and the 365-day generator, so absolute numbers are inflated): app start 5.1 s; **first save 59.8 s**; save p50 3.4 s, p95 16.4 s; checks run 0.8 s; daily report 0.3 s / Plus 0.4 s; digest 0.7 s; bank match 3.6 s; ageing 0.1 s. (`before30.json` in the bench folder.)
- Profile of the hook on y30 (`C:/Users/Asus/AppData/Local/Temp/claude/c--Users-Asus-Projects-PetrolPumpERP/debfa87f-7f7b-467e-88f6-8bfc46d00e7e/scratchpad/prof.py`): the FIRST run for a day takes ~15 s, the second ~1.5 s. First run is slow because `check_service.record` writes a new row plus an audit row per check (747 checks over 2 days; 1630 separate commits, 6 s in sqlite commit alone, 4 s in `audit_log_repository.get_latest_entry`). Credit checks (25 customers, full bill history) are 12.9 s of the 15 s on the first run, 1.0 s on the second. This is the likely root of the "first save is slow": every check result is committed one by one, each with its own audit row.
- Idea for the fix (not started): (a) background worker with debounce, only the changed day(s); (b) record all of a day's specs in ONE transaction; (c) credit checks as one grouped SQL query instead of per-customer ORM scans; (d) indexes (sales.customer_id/payment_method/status, check_results latest lookup, audit_logs created_at) in a new migration.

Baseline test counts: web Vitest passed (count line lost, audit says 388); desktop Vitest 46; Python baseline running in a worktree of the tag (`C:/Users/Asus/AppData/Local/Temp/claude/c--Users-Asus-Projects-PetrolPumpERP/debfa87f-7f7b-467e-88f6-8bfc46d00e7e/scratchpad/base_py.txt`); Playwright baseline not yet run.

Still running in the background while paused (harmless, only read the repo copy): the Python baseline pytest, the 365-day generator. The demo Electron window (demo DB in the scratchpad) may still be open.
