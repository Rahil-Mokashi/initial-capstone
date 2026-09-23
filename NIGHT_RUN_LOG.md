# Overnight Autonomous Run Log

Session started 2026-09-23 per night_prompt.txt, working through tasks in order on
feature/core-framework. Never pushes; all commits are local for the user to review.

## Task 1 - Bulk attendance marking via inline buttons

Found already implemented and uncommitted in the working tree at session start (from
an earlier interrupted run) - `app/ui/attendance_window.py` and
`tests/test_attendance_ui.py` already had the full change. Verified rather than
re-implemented:

- Roster now lists every active employee for the selected date, not just those
  already marked. Employees with no record yet get inline "Present"/"Absent" buttons
  in the status column; employees already marked show their status text and the
  existing per-row edit icon (opens the correction dialog), same as before.
- "+ Mark Attendance" dialog is untouched (`_open_mark_dialog`, line 192) - still the
  path for Late/Half Day/Leave/Holiday and for corrections.
- Inline buttons are gated on `self._can_manage` (`ATTENDANCE_MANAGE` permission),
  exactly the same flag that already hides `mark_button` - a view-only role sees
  "Not marked" text instead of buttons (verified by
  `test_inline_quick_mark_hidden_for_view_only_role`).
- `_quick_mark` calls `AttendanceService.mark_attendance` as-is, one call per click -
  no bulk-insert path, matching the "don't over-engineer" instruction for a
  roster of a few dozen employees.
- Tests: 3 new UI tests added (present button marks correctly, absent button marks
  correctly, buttons hidden for view-only role) plus the existing "no records for a
  date" test updated to expect the full roster with quick-mark widgets instead of an
  empty table.

Test count: 878 passed before this task's commit (already included the uncommitted
diff) -> 878 passed after (no change, since the work was already present and green).

Commit: `055ccc8 feat: mark daily Present/Absent inline on the attendance roster`

Judgment call: treated the pre-existing uncommitted diff as this task's output rather
than redoing it, since it already satisfied every bullet in the task spec and was
green. No scope was added beyond what was already there.

## Interruption: concurrent run, then a power cut

Between Task 1 and Task 2, this session (running interactively in a second VSCode
window) and the `run_overnight.ps1`-launched headless run above were both active on
this same repo at once, unaware of each other - confirmed via two live `claude.exe`
processes and a duplicate/near-identical commit for Task 1 (`4cb59ea` from this
session, `055ccc8` from the headless run, which swept up this session's already
in-progress, uncommitted Task 2 UI edits into its own Task-1-labeled commit - see
below). Flagged to the user, who then confirmed the headless run had stopped because
of an overnight power cut, not because it finished, and asked this session to resume
the task list alone from here. No further concurrent-run risk from this point on.

## Task 2 - Migrate Attendance.shift_label to a real Shift foreign key

**Commits:** `bc67d37` (model/migration/service/schema/DI wiring/service tests) plus
the UI half already present in `055ccc8` (see "Interruption" above - attendance_window.py's
Shift dropdown and test_attendance_ui.py's shift_service wiring were written by this
session before the interruption, then committed by the other run under its Task-1
message when it swept the whole dirty tree). Both commits' actual file contents are
exactly what this task intended; only the git history labeling is tangled by the
interruption, not the code itself.

**Tests:** 883 passed (full suite, before committing) - includes 4 new
`test_attendance_service.py` tests (mark/correct with a valid shift_id, mark/correct
rejecting an unknown shift_id) and 2 new `test_attendance_ui.py` tests (mark dialog
saves the selected shift, correction dialog preselects the record's existing shift).

**What changed:**
- New Alembic migration `9f3c7a1b2d4e` adds `attendance.shift_id` (nullable FK to
  `shifts.id`) and backfills it: exact same-day `shift_label` match when more than one
  shift exists that day, otherwise the sole shift that day if there's no ambiguity,
  otherwise left NULL. Verified against a scratch copy of the real dev DB (never the
  original) before writing it into the model - correctly matched 1 row by label and
  correctly left 1 row unmatched (two shifts that day, no label to disambiguate),
  and the downgrade/upgrade round-trip was also exercised.
- `shift_label` is kept on the model, not dropped - it's the historical free-text
  record for rows that can't be confidently matched, and dropping historical data is
  against project rules regardless of how minor the field.
- `AttendanceService.mark_attendance`/`correct_attendance` now validate `shift_id`
  against `ShiftRepository` the same way `employee_id` is already validated, raising
  `NotFoundError` for an unknown shift rather than letting a bad FK reach the DB layer.
- `AttendanceMarkDialog`'s free-text "Shift" field became a dropdown of real Shifts
  for whichever date is selected (reloads on date change); `AttendanceCorrectionDialog`
  gained the same dropdown, preselected to the record's existing shift if any.
- `AttendanceService.__init__` gained a `shift_repo` parameter - updated the one
  production call site (`main_window.py`) and both test fixture files.

**Judgment calls:**
- The task's own wording ("match by date if there's a same-day Shift record") is
  ambiguous when more than one shift exists on a date (e.g. Morning + Evening) -
  matching purely by date in that case would silently pick the wrong one. Added a
  same-day exact-label match as the first, more specific check, falling back to "the
  sole shift that day" only when that's unambiguous, and leaving `shift_id` NULL
  otherwise rather than guessing - the real dev-DB test above confirms this happens
  in practice, not just in theory (73 seeded shift rows, one attendance record on a
  two-shift day correctly left unmatched).
- Chose not to make `shift_id` required or to remove the ability to mark attendance
  without picking a shift: Shift rows are opened separately (Phase 7) and aren't a
  prerequisite for marking who was present, so requiring one would block the common
  case Task 1 just streamlined.
- Gated the new Shift dropdown on nothing beyond what `ATTENDANCE_MANAGE` already
  requires - checked the role/permission matrix first: every role holding
  `ATTENDANCE_MANAGE` (Manager, Shift Supervisor, Admin, Owner) already holds
  `SHIFT_VIEW` too, so no one who could reach this dialog before is newly blocked.

## Task 3 - Decide ADMIN vs OWNER permission divergence

**Commit:** `c5f6440` - `docs: decide ADMIN and OWNER stay permission-identical, guard it with a test`
**Tests:** 885 passed (full suite, before committing) - includes 2 new RBAC tests.

**The decision: keep them identical.** No code change to `ROLE_PERMISSIONS` was
needed - `ADMIN` and `OWNER` already both resolve to `tuple(Permission)` and this
task's job was to turn "flagged as worth a deliberate decision" into an actual,
documented decision rather than a silent default.

**Why:** this app is scoped to a single petrol pump throughout (problemstatement.md,
ARCHITECTURE.md, every phase built so far) - nothing in the requirements, the
confirmed business rules, or six roles' actual real usage across the codebase ever
distinguishes what an Owner may do that an Admin may not. The one place the original
requirements gesture at Owner-specific authority (problemstatement.md #21's
discrepancy workflow, step 6, "Owner approval where required") was already
deliberately folded into a single Manager/Admin/Owner-shared `RECONCILIATION_APPROVE`
permission back in Phase 15, not an Owner-only gate - reopening that split now,
without a real requirement driving it, would be inventing a business rule instead of
following one (explicitly against CLAUDE.md's Development Rules).

**What changed:**
- `PROJECT_CONTEXT.md`'s Known Limitations bullet on this topic rewritten from an
  open flag into the actual decision and its full reasoning, plus a pointer to where
  to revisit it (a second location or outside investor introducing a real
  financial-visibility split) and which test to update if that day comes.
- Two new tests in `tests/test_auth_rbac.py`: `test_admin_and_owner_are_deliberately_identical`
  (compares the `ROLE_PERMISSIONS` constant directly) and
  `test_admin_and_owner_seeded_roles_hold_the_same_permissions` (compares what's
  actually seeded into the DB for both roles, and that it's the full permission set).
  Together these mean a future accidental divergence fails a test instead of drifting
  in silently - and a *deliberate* future split has to touch this test in the same
  change, which is the point.

Judgment call: this is the "keep them the same, document why" branch of the task's
two allowed outcomes, not the "split them" branch - picked because nothing in the
existing codebase/docs supports inventing a specific split, and the task said to
pick whichever reading is best supported rather than defaulting to a split just
because one was offered as an option.

## Task 4 - Extend PDF/Excel export to remaining reports

**Commit:** `2f06085` - `refactor: move Fuel Type Summary report onto the shared export pattern`
**Tests:** 887 passed (full suite, before committing) - includes 1 new CSV-export test
in `test_report_export.py` and 1 new CSV-writes-a-file UI test in `test_report_ui.py`.

**Survey first:** checked every report method in `report_service.py` (11 total) against
`report_window.py`'s Reports Hub and found all 10 `TableReport`-returning methods
already wired through the shared `TableReportWindow`/`report_export.py` pattern (the
six Phase 16 reports plus the five later cross-module ones). Only `get_fuel_type_summary`
was still on its own bespoke exporters (`export_fuel_summary_pdf`/`export_fuel_summary_excel`
in `report_export.py`) - exactly the gap ROADMAP.md's Next Immediate Task #6 and its
own CSV-export note already named by file and reason. Also checked for report-shaped
screens with *no* export at all (e.g. the Audit Log viewer) - found one, but left it
out of scope: it was never listed anywhere as a report with a missing-export gap, and
adding export to a screen that never had any is a materially different, larger task
than "wire the ones with bespoke exporters onto the shared one," which is what this
task and ROADMAP's own wording actually describe.

**What changed:**
- `report_export.py`: replaced `export_fuel_summary_pdf`/`export_fuel_summary_excel`
  (~90 lines of PDF/Excel-building code duplicating `export_table_pdf`/`export_table_excel`)
  with one small `fuel_summary_to_table_report()` that reshapes the report's own
  `FuelTypeSummary` list into the generic `TableReport` shape, reusing the existing
  `_fuel_summary_rows` row-building helper.
- `report_window.py`'s `FuelTypeSummaryReportWindow`: PDF/Excel/Print buttons now call
  the shared `export_table_pdf`/`export_table_excel`/`build_table_report_html` through
  that conversion, and it gained a fourth button, **Export CSV** (`export_table_csv`) -
  the one thing every other report already had that this one didn't.
- The on-screen card layout (`FuelTypeSummaryCard`, one card per fuel type) was
  deliberately left untouched - this task is about the export mechanism, not a
  restyle, and the cards are a better on-screen presentation than a raw table for
  this particular report.
- Updated `PROJECT_CONTEXT.md` (Phase 17 section) and `ROADMAP.md` (the CSV-export
  bullet and Next Immediate Task #6, both closed out) to match.

Judgment call: kept the bespoke on-screen card UI and only converged the *export*
code path, rather than replacing the whole window with a generic `TableReportWindow`
(which would trade the cards for a plain table). The task's own wording is about
reusing the export pattern, not about visual uniformity, and CLAUDE.md's "never
rewrite working code unnecessarily" argues against discarding a UI that already
works well just to make every report look identical.

## Task 5 - General UI simplification pass (one file per commit, 90-minute budget)

Scanning strategy: grepped every `app/ui/*_window.py` for files that have both a
per-row `make_edit_icon_button` (the app's established one-click row action) and a
`_selected_*`-style "read the currently selected table row" helper - that
combination is the fingerprint of a top-level button requiring select-then-click
sitting next to a row-level action that already does the same thing in one click,
the exact "redundant clicks to reach common info/action" pattern this task asks
about. Working through the matches in order.

### fuel_price_window.py

**Commit:** `c95dc2c` - `style: drop the redundant top-level Change Price button`
**Tests:** 891 passed (full suite, before committing) - includes a brand-new
`tests/test_fuel_price_ui.py` (4 tests), since this window had no UI test coverage
at all before this pass.

**What changed:** the top "Change Price" button required selecting a fuel's row
first, then clicking the button (2 actions) - but every row already has a per-row
pencil-icon button (`make_edit_icon_button`) that opens the exact same
`FuelRateDialog` for that row's fuel in 1 click, gated on the same
`FUEL_PRICE_MANAGE` permission. Removed the top button and the now-unused
`_change_price` method; kept `_selected_fuel` (still used by "Price History", which
has no per-row equivalent) and `_change_price_for` (now the single, shared entry
point both the removed button and the row icon used to call).

**Why this is simpler:** changing one fuel's price is now always 1 click instead of
up to 2, with no loss of discoverability - the per-row icon was already there and
already the documented, established convention this app uses for row-level actions
(see `qt_utils.make_edit_icon_button`'s own docstring on why double-click-to-edit
was replaced with a visible icon everywhere else). Same permission check
(`FUEL_PRICE_MANAGE`), same dialog, same audit logging - nothing about *what* the
action does or who can do it changed, only how many clicks it took to get there.

Judgment call: added a new test file rather than skipping tests for this change,
since CLAUDE.md requires tests for changes to a module and this window had zero
existing coverage - the four tests cover the button's removal, the row icon still
opening the dialog, the icon being hidden for a view-only role, and the dialog
itself still saving correctly.
