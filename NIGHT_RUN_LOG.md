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
