# Software map: what each part is for, and where it lives

Written for: the pump owners and whoever maintains the software. One page, no jargon where it can be avoided.

## 1. The three kinds of screens

Almost everything the software does falls into one of three rhythms. If a screen is not on this list it is a setting you rarely open.

| Rhythm | Who | Screens |
|---|---|---|
| **Every shift** (the cashier / data entry) | `DATA_ENTRY` | **Terminal** (credit bills as they happen) -> **Close Shift** (closing readings, cash, card and phone-pay totals, tally and shortage on one screen) -> **Expenses** -> **Oil / Lubricants** -> **Bowser Van** -> **Advance, Final and bank deposits** |
| **Every day** (manager, owner, accountant) | managers, owners, accountant | **Today** (what needs attention), **Checks** (every verification, failures first), **Daily Report** (Classic / Plus, print, PDF), **Credit** (who owes, ageing, follow-ups) |
| **Now and then** | owner, accountant, admin | Bank Matching, Payroll, Employees, Fuel Prices, Tanks, Procurement, Reports, Owner Choices, Backups, Audit Log, Users, **Devices** (PCs allowed on the Main PC) |

The cashier's menu is deliberately short: `DATA_ENTRY` does not see masters, prices, reports or approvals.

## 2. What happens when a shift is closed

1. During the shift: each **credit bill** is typed on the Terminal (customer, bill number, amount). Nothing else is typed per sale.
2. After the shift, on **Close Shift**: the **opening reading is the previous closing reading** (filled in for you; typed only the first time a nozzle is ever used). Type each nozzle's **closing master reading**. **Testing** (5 litres by default, setting `default_testing_litres`) is poured and goes back into the tank; the meter counts it, so it is taken off the litres sold and never leaves the tank.
3. Type how the money was collected: **Advance** and **Final** (cash handed to the office), and the **Card / DTP Card / Phone Pay / PTM / Other** totals.
4. The **tally** beside the form uses the owner's own formula from the paper report:
   `Credit sales + CARD + DTP Card + Other + PHONE PAY + PTM + Expenses + Advance + Final = Total Sale`.
   The difference is shown at once as **Balanced**, **Short Rs X** or **Excess Rs X**. Nothing is saved while you type; **Close shift** saves everything together or nothing.
5. The **checks** run after every save and show up on Today / Checks.

## 3. Where things live in the code

| You want to change... | Look in |
|---|---|
| A business rule (how a thing is calculated or what is allowed) | `app/services/` (one file per area, for example `close_desk_service.py`, `credit_control_service.py`, `payroll_service.py`) |
| A choice the owners make (rounding, credit over the limit, usual testing litres...) | `app/services/pump_settings_service.py`: each has a questionnaire ID (T-01, V-14, T-15 ...) and shows under **Owner Choices** |
| A verification the owners can see (Checks) | `app/services/check_service.py` (engine) and `report_checks.py`, `credit_checks.py`, `bank_checks.py`, `payroll_checks.py` |
| What the web screen asks the Main PC for | `api/routers/` (thin: no rules, they only call a service) |
| A screen | `web/src/features/<area>/` (one folder per screen; its test sits beside it) |
| The menu and who sees what | `web/src/components/nav.ts` and the roles in `app/core/constants.py` |
| The window, printing, the network client | `desktop/src/` |
| Several PCs on the network | `api/lan/` and `docs/adr-lan-multi-user.md` |
| The database layout | `app/models/` + a new file in `alembic/versions/` (made with `python scripts/new_migration.py "message"`; never edit an old one) |

Rules that keep it understandable: **a screen never contains a rule; a router never contains a rule; a service never deletes history** (it voids, reverses or adjusts, and writes the audit log).

## 4. How to find your way

* `PROJECT_CONTEXT.md`: current state and decisions. `TWELVE_HOUR_REPORT.md`: what was built after the site visit and what the owners still have to answer.
* `docs/screenshots/`: pictures of the screens on made-up data.
* To see a screen working on made-up data: `python desktop/e2e/seed_demo_day.py` (with `PETROL_PUMP_DB_PATH` pointing at a new file), then start the app against that file.
