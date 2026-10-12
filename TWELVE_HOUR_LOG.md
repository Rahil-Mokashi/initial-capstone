# Twelve-hour site-visit build log

**Started: 2026-10-12 23:42 (local, IST).** Branch for the work: `feature/site-visit-build` (created in Track 0).
Source brief: `PROMPT_12H.md` (gitignored). Restart rule: read this file, continue from the first unfinished step.

## Preflight findings (Track 0)
- `SITE_NOTES.md`, `PROMPT_12H.md`, `run_12h.ps1`, `private_samples/` were **not on disk** at start. The brief and notes arrived as pasted text (the notes paste was cut off after "Hard requirements"); I saved both as gitignored files. **No private figures or photos exist on this machine**, so the PRIVATE regression test (Track 2) can only be written to skip cleanly; the formulas come from the brief and `docs/daily-report-spec.md`.
- `OWNER_ANSWERS.md`, `SECURITY_REPORT.md`, `FIX_BATCH_PROMPT.md`: absent. `FIX_BATCH_REPORT.md` present, so the fix batch is not pending.
- Working tree was clean; started on `feature/js-frontend`.
- Commit 1: `.gitignore` now covers the four private inputs. `git ls-files` shows none tracked.
- Baseline run found a date-fragile test (`tests/api` hard-coded `shift_date` 2026-10-11, which was "today" only yesterday): fixed to use today's date.
- Existing code already has: `ACCOUNTANT` role, 8 seeded `Tender`s (Cash, Credit, Card, DTP Card, PhonePe, Paytm, Expenses, Other), `ShiftCashBook` (Advance/Final), `ShiftBankDeposit`, shortage recoveries, credit accounts. The brief says "add the role ACCOUNTANT"; it already exists, so I only add new permissions to it.

## Track 0 result (elapsed ~0h35 at 00:17)
- Commits: `c299f3e` gitignore, `923fd87` test date fix, `6c49542` RESET_POINT. Tag `reset/pre-12h-2026-10-12` -> `923fd87`. Bundle `..\PetrolPumpERP-pre-12h-2026-10-12.bundle` verified okay (14.9 MB). Branch `feature/site-visit-build`.
- **Baseline counts** (before): Python **1523** passed (18m17s, no hang; before the date fix 1 test failed); web Vitest **317**; desktop Vitest **33**; Playwright **46** passed, 8 opt-in skipped.
- Judgment: the full Python suite takes ~18 min, so I run targeted tests per step and the full suites once at the end of each track.

## Track 1 (started ~01:05, elapsed ~1h25)
### Commit: checks engine, owner settings, DATA_ENTRY role
- Added: `CheckResult`/`CheckExplanation` (append-only), `PumpSetting` key-value table with a registry of owner decisions (`rounding_rule` T-03/T-04, `add_testing_back` T-01, `internal_fuel_deducts_tank` T-12, `credit_over_limit` V-14, `daily_report_style`, `dip_tolerance_percent` T-02, bank tolerance/window H-09/H-02, `new_customer_approval` V-10), `CheckService`, role `DATA_ENTRY`, permissions `check.view`/`check.explain`, one Alembic migration (`3c4f91bf20be`), and a test that fails if models and migrations ever disagree.
- Tests: new `tests/site` = 17 passed. (Suite-wide counts at the end of the track.)
- Judgment calls:
  - **ACCOUNTANT already existed**, so nothing was added; it (and MANAGER) gained `check.view`/`check.explain` only. OWNER/ADMIN get every permission automatically.
  - **DATA_ENTRY added** (SHIFT_SUPERVISOR carries attendance/leave management, wrong for a cashier). Permissions: shift/sale/expense/reconciliation view+manage, credit view, inventory/nozzle/fuel-price/employee/settings view. No approvals, no users, no prices, no shortage booking. **NEEDS HUMAN REVIEW (V-03, V-04).**
  - Several OWNER logins already work (any number of users per role); a test pins it. Approvals already record the acting user.
  - Settings live in a new table instead of new columns on `AppSetting`, so the existing model and migrations stay untouched.
  - A check with a missing side (expected or actual unknown) is a FAIL, never a pass.
