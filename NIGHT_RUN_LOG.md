# Overnight Run Log — 2026-09-23

Autonomous overnight session on `feature/core-framework`. Rules: one focused commit
per task, full `pytest` green before every commit, never `git push`, log every
judgment call here. See the session's original task list for full task text.

## Housekeeping — before Task 1
Found one pre-existing uncommitted change on the branch at session start: a
`PROJECT_CONTEXT.md` edit recording the 2026-09-16 session's state, never committed.
It was unrelated to tonight's work and looked like real, finished documentation (not
a work-in-progress draft), so committed it as-is (`3b36466`, `docs: record 2026-09-16
session state and open follow-ups`) to start tonight's tasks on a clean tree, rather
than folding it into a later commit or leaving the tree dirty all night.

## Task 1 — Bulk attendance marking via checkboxes
**Commit:** `4cb59ea` — `feat: mark Present/Absent inline on the attendance roster`
**Tests:** 875 → 878 (full suite green both before and after)

**What changed:** `app/ui/attendance_window.py`'s roster (`AttendanceWindow.refresh`)
used to list only employees who already had an `Attendance` row for the selected
date — so the table was empty until you'd already used "+ Mark Attendance" at least
once. Rebuilt it to list every **active** employee for the selected date:
- A row with no `Attendance` record yet shows two small buttons, **Present** and
  **Absent**, directly in the Status column instead of a status label. Clicking
  either calls `AttendanceService.mark_attendance` for that one employee immediately
  — no dialog. One click = one employee marked, for the whole roster.
- A row that's already marked shows the status text and the existing edit-icon
  button (unchanged) for the correction dialog.
- The buttons only render when `ATTENDANCE_MANAGE` is held (`self._can_manage`) —
  identical gating to today's dialog path. A view-only actor sees a plain "Not
  marked" label instead of buttons, never an interactive control they can't use.
- "+ Mark Attendance" dialog is untouched — still there, still the only path for
  Late/Half Day/Leave/Holiday and still reachable for Present/Absent if someone
  prefers it.
- No service-layer change: reused `AttendanceService.mark_attendance` exactly as
  the dialog already called it, one call per click. Roster sizes here are "a few
  dozen employees" per the task brief, so N individual calls needs no bulk-insert
  path.

**Judgment calls:**
- Filtered the roster to `EmployeeStatus.ACTIVE` only (excludes on_leave/suspended/
  terminated). Marking daily attendance for someone already recorded as on leave,
  suspended, or terminated isn't a real workflow this app has anywhere else, and
  the task didn't ask me to invent one.
- Updated `tests/test_attendance_ui.py::test_window_shows_records_marked_for_selected_date`,
  which previously asserted an empty roster (`rowCount() == 0`) for a date with no
  records — that assertion was testing the exact behavior this task asked me to
  replace, so I changed it to assert the new (correct) behavior: the employee still
  shows up, unmarked, with quick-mark buttons instead of a status. Added three new
  tests: Present button marks correctly, Absent button marks correctly, buttons are
  absent (literally, a "Not marked" label instead) for a view-only role.
