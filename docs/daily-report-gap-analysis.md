# Daily report: gap analysis (Classic replica)

Written at the start of Track 2 of the site-visit build (2026-10-13). For every field on the owner's two-sided daily
report: where it comes from in the data model today, or what is missing and what was added. Formulas are the ones
in `docs/daily-report-spec.md` and the site-visit brief. No private figures are used or quoted here.

Rule followed throughout: **reuse the existing services as they are**; add only what the report needs, as new
tables and services; never change an existing rule. Anything the owner has not decided is a setting
(`app/services/pump_settings_service.py`) tagged with its questionnaire ID.

## Correction to an older rule
`PROJECT_CONTEXT.md` recorded "fuel only, no other retail" (owner answer of 2026-08-18). The report proves lubricants
**are** sold and stocked per item (K-09), and their rupees are part of "Total Sale". That old rule is left in place
as history; lubricants are a **new module** next to fuel, not an edit of the fuel rules.

## FRONT

### Sale details grid
| Field | Source | Status |
|---|---|---|
| Column heads MS-22, MS-16, HSD-16, HSD-22 | `Tank.code` (kept as data, never hard-coded; V-18 open) | **Have** (needs the four tanks created at set-up) |
| O/S (opening stock, litres) | Tank stock now minus every signed `TankTransaction` since the start of the local day | **Have** (derived) |
| Purchase | `TankTransaction` of type RECEIPT that day | **Have** |
| Shift 1 / Shift 2 litres | Completed `Sale.quantity` per shift and tank (`Sale.nozzle.tank_id`); the cashier closing a nozzle auto-settles the rest of the meter as one cash sale, so litres billed = litres metered less testing | **Have** |
| Testing | `NozzleAssignment.testing_volume` per tank | **Have** |
| Total Stock | O/S + Purchase - Shift1 - Shift2 (testing NOT added back; setting `add_testing_back`, default off, T-01) | **Computed in report builder** |
| Closing Stock (dip) | Latest `TankReading.physical_stock` of the day, else the day's `FuelReconciliation.physical_stock` | **Have** |
| (+/-) | Closing Stock - Total Stock | **Computed** |
| Total column (litres) | Sum of the tank columns | **Computed** |
| Oil (Rs) per shift | Lubricant sales of that shift | **MISSING -> new lubricant module** |
| Total Sale (Rs) per shift | Fuel rupees (sum of completed `Sale.amount` in the shift) + Oil | **Computed** (fuel part have; oil missing) |
| Total Rs | Sum of shift Total Sale - sum of Oil | **Computed** |

### Shift N transaction details
| Line | Source | Status |
|---|---|---|
| CreditSale | Completed credit `Sale.amount` in the shift (includes the Stock Transfer to the bowser) | **Have** |
| CARD, DTP Card, Other, PHONE PAY, PTM | Per-mode totals typed by the cashier for the shift | **MISSING -> new `ShiftTenderEntry`** (tenders already seeded; sales only carry cash/credit/UPI-as-"Other") |
| Expenses | Pending + approved `Expense.amount` of the shift (rejected excluded; pending flagged by a check) | **Have** |
| Advance, Final | `ShiftCashBook.advance_amount` / `final_amount` (typed cash collections already; T-06) | **Have** (no new model needed) |
| Total | Sum of the lines; must equal the shift's Total Sale (check) | **Computed + check** |

The sample's 3-decimal total (T-03) cannot occur here: every bill is rounded to paise (`app/core/money.py`) before it
is stored, and totals are sums of rounded lines (setting `rounding_rule`, default per bill).

### Shift N cash book
| Field | Source | Status |
|---|---|---|
| Opening Balance | `ShiftCashBookService.get_opening_balance` (previous shift's cash in hand) | **Have** |
| Advance, Final | `ShiftCashBook` | **Have** |
| Other receipts ("cash short return (name)") | `EmployeeShortageRecovery` rows posted into the cash book | **Have** |
| Bank deposits, bank shown | `ShiftBankDeposit.bank_name` / `amount` | **Have** |
| Cash in hand | Derived by the service | **Have** |

### Credit sale, per shift
Bill No = `Sale.receipt_number`; Name = customer; Amount; Total = CreditSale. **Have.** The Stock Transfer to the bowser
is recorded as a credit sale to an internal "Stock Transfer (Bouser)" customer through the normal sale service (so it
leaves the tank, counts in Total Sale and shrinks the cash remainder). **Link table MISSING -> new `BowserTransfer`.**

## BACK

### Expenses details
Lines come from `Expense` (category + description). Needed extras:
- **Internal fuel use** (vehicle / genset / Omni, litres): **MISSING -> new `InternalFuelUse`** (expense id, litres, vehicle).
  Recorded as an expense at selling price with litres and **not** deducted from tank stock (it already passes the nozzle
  meters; T-12, setting `internal_fuel_deducts_tank`, default off). The older `Expense.tank_id` path (which does deduct)
  is untouched and is not used for this.
- Named cash shortages: `EmployeeCashShortage` already creates an expense. **Have.**
- Lubricant rate discounts, tea, trips, repairs: ordinary expenses. **Have.**

### Oil sale
Name, Opening, Purchase, Sale, Balance, Rate, Total, Shift, Customer. **MISSING -> new `LubricantItem` + `LubricantMovement`
(purchase / sale / adjustment, append-only).** Balance = Opening + Purchase - Sale; Total = Sale x Rate (rounded to paise per line).

### Bowser van
| Part | Source | Status |
|---|---|---|
| A] Internal stock: opening + each Stock Transfer (litres, Rs) | Opening = previous day's closing (override allowed); transfers = `BowserTransfer` | **MISSING** |
| B] Bills: Bill No, Cust Name, Qty, Amount, Transport, Total | `BowserBill` (customer is a normal credit customer) | **MISSING** |
| Closing Stock | A total litres - sum of B Qty | **Computed** |
| C] Meter: Start, Testing, End, Net Sale | `BowserMeterReading` | **MISSING** |
| Net Sale = End - Start - Testing; must equal sum of B Qty | Computed + check | **Check** |

## Things that are settings, not decisions made here
`rounding_rule` (T-03/T-04), `add_testing_back` (T-01), `internal_fuel_deducts_tank` (T-12), `dip_tolerance_percent` (T-02),
`daily_report_style` (Classic default).

## Open questions this analysis raises
- Which product (including "Power") sits in MS-22 and MS-16: V-18. Labels are tank codes, so it does not matter for the report.
- How the bowser's opening stock is valued in rupees (T-13). Default: previous closing litres x the previous day's average transfer rate; manual override.
- Whether expenses entered but not yet approved belong on the printed report (T-14). Default: included, flagged by a check.
- Bill numbers: the old series (10292...) vs the app's receipt numbers (Q7 in the spec). Default: the app's receipt number.
