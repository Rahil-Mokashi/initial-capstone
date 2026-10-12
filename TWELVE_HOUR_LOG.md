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
