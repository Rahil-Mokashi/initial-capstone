# App walk-through, 17 Oct 2026: what was done with each note

Source: Rahil's audio notes (items numbered 1 to 36 in the order they were heard). Branch `feature/pilot-prep`, never pushed. Commit hashes are in the status table. P1 = before the pilot, P2 = first week, P3 = later.

Status words: **done**, **partly**, **not done**, **waiting on owner** (built with a default and saved as an Owner Choice; needs the owners to confirm).

## Status of items 1 to 36

| # | Note | P | Status | Commit |
|---|---|---|---|---|
| 1 | Login: remove the left-side subtext (heading kept) | P1 | done | efddede |
| 2 | Login: bottom left shows only the device name | P1 | done | efddede |
| 3 | Login: no language toggle at all (Hindi button removed) | P1 | done | efddede |
| 4 | Dark and light mode | | OK, unchanged | |
| 5 | "Can't sign in? Ask…" | | OK, unchanged | |
| 6 | Show password hides again after 3 s | P1 | done | efddede |
| 7 | PIN sign-in and Forgot password | | OK, unchanged | |
| 8 | Overall login look | | OK, unchanged | |
| 9 | Network setup: plain words (Client says it keeps no data) | P1 | done | 8190866 |
| 10 | Network setup guide (Word and Markdown, diagrams, screenshots) | P1 | done: `docs/guides/NETWORK_SETUP_GUIDE.docx` and `.md` | 18b0a4d |
| 11 | App-wide search: typos, plain words, every screen, common actions, records | P1 | done | faf9cf6 |
| 12 | Remove the "Offline · Local" chip | P1 | done (a Client PC still shows its link state) | efddede |
| 13 | Date and time | | OK, unchanged | |
| 14 | Alerts can be cleared: Open, Resolve (automatic), Acknowledge with a reason, who and when | P1 | done | 22b3866, 97c0b22 |
| 15 | Cash-short alert: who handed in, "Mark against <name>", resolves it, amount owed and recovered on the employee page | P1 | done; the payroll deduction itself is not built, as asked | 22b3866, 97c0b22, 8b5f1b8 |
| 16 | Same buttons on the Today "most urgent" card | P1 | done: the Today page's "Needs action" section uses the same alert cards | c55175e |
| 17 | User menu: device name, mode, app version | P1 | done (nothing else added) | 06103b7 |
| 18 | Digest and Today numbers must stay inside their boxes | P1 | done and tested (1024, 1366 and 1920 wide, light and dark, ₹99,99,999.99 and 99,999.999 L) | c55175e |
| 19 | "Waiting for you" / "Open review" says what and how many | P1 | done: "3 entries need your check, Review" | c55175e |
| 20 | Today page: fewer sections, a clear order | P1 | done: needs action, today's sales, shifts and who is on them, tank levels, credit to chase; the rest behind "More" | c55175e |
| 21 | Polish screen by screen | P2 | not done | |
| 22 | Employees | | OK, unchanged (the employee page gained a Cash shortages section) | 8b5f1b8 |
| 23 | Users: show password rules before Save | P1 | done: the rules were already under the field; wording made plainer and added to Reset password | 06103b7 |
| 24 | Users (deactivate, reset, codes) | | OK, unchanged | |
| 25 | Fuel prices | | OK, unchanged | |
| 26 | Tanks drawn as underground horizontal tanks, numbers on tap, level from the dip chart or the round-tank formula; dip chart entry | P1 | done | bf7da96, b9ff4ee |
| 27 | Tank names MS-22, MS-16, HSD-16, HSD-22 in defaults, seed and demo data | P1 | done for the demo seed and the screen hints; `seed_e2e.py` (test data) still uses T1 and T2 on purpose | bf7da96 |
| 28 | Tank page wording ("6,240 L in the tank (book stock)") and one line for each action | P2 | done | b9ff4ee |
| 29 | Nozzle management | | OK, unchanged (up to 4 nozzles per dispenser is now Owner Choice S-01) | 3293f6b |
| 30 | Suppliers | | OK, unchanged | |
| 31 | Company profile: one line saying what it is for | P2 | done | 99630c4 |
| 32 | Full user guide (Word, PDF-ready and Markdown) | P1 | done: `docs/guides/USER_GUIDE.docx` and `.md` (a PDF can be saved from Word) | 18b0a4d |
| 33 | Terminal: only Credit and DTP Card; Cash, UPI and card come from shift totals | P1 | done | 99630c4, 126afc2 |
| 34 | Credit sale to a new walk-in customer: create on the spot, owner approves, matched against existing | P1 | done, **waiting on owner** (W-34) | 99630c4, 2f3f5e8 |
| 35 | Receipt after a sale | | OK, unchanged (it now also shows the vehicle number) | 126afc2 |
| 36 | Vehicle number required on Terminal sales | P1 | done: a real column, moved out of remarks by a migration | 126afc2 |

Also done because the work depended on it (Step 0): Close Shift now closes the shift (b33756e predecessor `245461b`), a check for a shift open more than 24 hours (`245461b`), "Checks updating" on every screen (`6290aa6`), a failing check stops a lock unless an owner gives a reason (`b33756e`, V-07).

## Step 0: what was and was not done before this round

| Question | Answer (evidence) |
|---|---|
| Close Shift actually closes the shift | Was **not** (`CloseDeskService.close` never changed the shift's status). **Now done**, all or nothing, tested (`test_saving_the_desk_closes_the_shift...`) |
| A "shift open more than 24 h" check exists | Was **not** (no such check in the code). **Now done**: `shift.open_too_long`, tested |
| The 365-day benchmark was re-measured | Was **not** (the generator stopped at day 60 when the run was paused). **Now done**: first save 0.17 s, a normal save 0.022 s (the audit measured 6.6 s). Numbers in `docs/bench/after365.json` |
| Tests cover the real background check path | **Yes**: `tests/api/test_api_check_worker.py` runs the real worker (the other tests use the test-only synchronous switch) |
| Screens show "checks updating" until fresh results arrive | Was **not**. **Now done**: `GET /api/checks/status` and a chip that refreshes every screen when the run ends |
| Locking a day waits for, or triggers, a fresh check run | Was **not**. **Now done**: the lock re-runs the day's checks first and refuses if one fails, unless an owner gives a reason (audit event `shift_lock_check_override`) |
| Per-attendant shortages work | **Partly** before: the service existed and worked from the Reconciliation screen, but nothing connected an alert or a Close Shift shortage to a person. **Now done** from the alert, the employee page, and Reconciliation |

## Owner Choices added (all need owner confirmation)

| ID | Choice | Default | Why this default |
|---|---|---|---|
| S-01 | Most nozzles on one dispenser | 4 | The site notes say 3 dispensers of 4 nozzles; the old rule of 2 refused it. The Qt app still stops at 2 |
| V-07 | A failing check stops a lock | Block (an owner can lock anyway with a reason) | The audit found a day with a failed check could be locked silently |
| W-33 | Attendants can use the Terminal | Off | Attendants hand in cash, UPI and card as totals; a sale they also typed would count that money twice |
| W-34 | New customer made at the counter | On (limit 0, first bill goes through, the next waits for an owner) | As instructed |

## Test counts

| Suite | Before (audit, 15 to 16 Oct) | After |
|---|---|---|
| Python, `tests/api` and `tests/site` | 976 passed | RESULT_PY_API |
| Python, everything else | 999 passed, 1 skipped | RESULT_PY_REST |
| Web (Vitest) | 388 | 409 |
| Desktop (Vitest) | 46 | 48 |
| Playwright | 58 passed, 10 opt-in skipped | RESULT_PW |

## Before and after pictures

* **After** (the finished screens, synthetic data): `docs/guides/img/` (53 pictures, for example `today.png`, `tanks.png`, `tanks-with-numbers.png`, `tank-detail.png`, `dip-chart.png`, `alerts.png`, `search.png`, `terminal-credit-new-customer.png`, `terminal-dtp.png`, `network-setup.png`). The layout test also writes full-page pictures of Today and More at three sizes in light and dark to `desktop/test-results/` when it runs.
* **Before**: `docs/screenshots/12h/today-owner.png` (the earlier Today page), `docs/js-tanks.png`, `docs/js-tanks-dark.png` and `docs/js-tank-detail.png` (the earlier tank cards and page). No new "before" pictures were taken for login, search, alerts or the Terminal.

## Noticed, not touched

* **A bug that was fixed because the lock guard depends on it:** the check "payment totals declared equal what the sales say" multiplied a Decimal by a float and crashed, which **silently stopped every check on any day that had a reconciliation** (the error was only logged). Fixed in `check_runners.py` with a test (`8b5f1b8`). Worth knowing: the audit's check timings were taken with this bug present.
* The Terminal API still accepts Cash, UPI and Card from office users (the screen offers only Credit and DTP Card). A cash sale typed there would add to the meter-based cash sale and count twice. Restricting it on the server is the right fix, but many tests and demo scripts build their data with cash Terminal sales, so it was left. Say if you want it.
* The Qt desktop app still caps a dispenser at 2 nozzles and still lists the older payment methods (it does not know DTP Card as a method).
* Alert details and check sentences show raw numbers ("7100.00 of 100000.00 litres remaining", "₹-80,000.00") without Indian grouping and with an odd minus sign. The cards and tiles I changed are grouped correctly.
* Reports and the digest take 2.7 to 3.3 s on a year of data (reads, not saves). The credit checks still scan each customer's bills one at a time (20 s on the first run of a year, in the background).
* "Mode" in the account menu says Main PC only when the request comes from this PC itself (127.0.0.1). If the Main PC's own window connects through its LAN address it would say Client PC. Not tried on real hardware.
* The dip stick figure typed on "Record reading" is still a free number; it is not converted through the dip chart.
* The Dip chart button is disabled for a role that may only look at tanks, so they cannot view the chart.
* `PROJECT_CONTEXT.md` said `seed_demo_data.py` was broken; it runs (after the tank rename it seeds four named tanks and no Power fuel).
* The installer, the Python service bundle and the Qt exe have **not** been rebuilt in this round. Rebuild the service (`pyinstaller api/pperp_api.spec ...`) before the installer, or the installer carries the old service.
* Several earlier unrelated things from the audit are still open: the pilot hardware steps, real printer test, opening balances for credit customers and cash in hand, the eight WhatsApp images in `docs/reference/`.

## Open owner questions

1. **Vehicle number**: kept in a real column now. Should an existing customer's vehicle list be kept (several trucks per customer)?
2. **DTP Card and other special methods**: only DTP Card was added. Do PTM or fleet cards other than DTP ever go through the Terminal? (PTM is Paytm, treated as UPI and collected by the attendant.)
3. **New counter customer (W-34)**: is a limit of ₹0 and "owner approves before the second bill" right? Who approves, and how fast?
4. **Failing check and locking (V-07)**: should a failing check stop a lock, or only warn?
5. **Attendants on the Terminal (W-33)**: confirm they never use it.
6. **Nozzles per dispenser (S-01)**: confirm 4.
7. **Dip chart**: do the owners have one from the oil company for each tank? It makes the pictures exact.
8. **Biometric machine** (item 33): brand, and can it export attendance? Then attendance could be imported instead of typed (P3).
9. **User menu**: only device, mode and version were added. Anything else?
10. **Acknowledging an alert hides it for the rest of that day only**; if still true tomorrow it shows again. Is that right, or should it stay hidden until the problem changes?
11. A cash shortage shows "who handed in the cash" as the people who worked that shift. If several attendants worked it, someone chooses. Should the Close Shift screen ask who handed in the cash?

## Alert counts by type, before and after (Step 2.4)

Measured with `scripts/bench/alert_counts.py` on the synthetic 365-day database (the owners' real database with its 28 alerts is not on this machine, so those 28 were not measured):

| Type | Before (every notification) | After (merged, minus acknowledged and booked) |
|---|---|---|
| low fuel | 1 | 1 |
| pending approval | 1 | 1 |
| attendance issue | 6 | 6 |

The synthetic data has no repeated alerts, so nothing merged here. The merging itself is proven by `test_the_same_alert_about_the_same_record_shows_once_with_a_count`. Run the script on a copy of the real database to get the real before and after.
