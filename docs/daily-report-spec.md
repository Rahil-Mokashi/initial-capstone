# Daily Report — Reference Spec

**Status: spec only.** No code, migrations, or model changes were made while writing this
document. Its purpose is to record, from the source materials alone, what this specific
pump's paper daily report actually tracks, and to check that against what
`app/models/` and `app/services/` in this repository currently do — not against what any
prior doc claims they do.

## Source materials

- `docs/reference/WhatsApp Image 2026-09-14 at 19.00.36.jpeg` and
  `...19.00.37.jpeg` — two halves of one handwritten "DAILY REPORT" sheet from a real
  shift (Sale Details, Shift 1/2 Transaction Details, two Cash Books, two Credit Sale
  tables).
- `docs/reference/...19.00.37 (1).jpeg` and `...37 (2).jpeg` — the second half of the same
  sheet: Expenses Details, Oil Sale, and the Bowser Van section (A/B/C).
- `docs/reference/...19.00.38.jpeg`, `...38 (1).jpeg`, `...38 (2).jpeg`, `...39.jpeg` —
  four screenshots of **Morex Technologies' web ERP** at `paintos.in/dmor/...`. Flagged
  up front rather than buried: this product's own branding and every module it shows
  (Paint Product Catalogue, 1K/2K Formulation Development, Production Batches, Dispatch
  Planning) is a **paint manufacturing/distribution ERP**, not a petrol pump system. It
  has no fuel, tank, nozzle, or shift-adjacent screen anywhere in the four captures. It
  is treated below only as a reference for generic web-ERP information architecture
  (a Masters / Operations / Reports left-nav, a Customer Payment Entry form, a
  per-customer ledger view with running balance) — not for any petrol-pump-specific
  content, because it has none.

---

## 1. The four product-tank streams: MS-22, MS-16, HSD-16, HSD-22

The Sale Details table's four data columns are headed `MS-22`, `MS-16`, `HSD-16`,
`HSD-22`. Read alongside the rest of the sheet (litre quantities, a shared `Rate`-driven
Rs total, two motor-spirit columns and two high-speed-diesel columns), these read as
**four physical tanks/grades**, not four abstract fuel types — "MS" (motor spirit/petrol)
and "HSD" (high speed diesel) each split into two streams, most likely two different
tanks or two different octane/spec grades per fuel, with "-22" and "-16" as some
site-specific suffix (see Open Questions — this isn't guessable from the sheet alone).

**How this repo models it:** `app/models/fuel.py` (`Fuel`, lines 9-30) is a flat
fuel-type lookup — a name string (`fuel_type`) plus one `rate_per_liter`. `app/models/
tank.py` owns capacity and current stock, with a `fuel_id` foreign key, so multiple
tanks can share one `Fuel` row (its own docstring says exactly this: "a pump can have
multiple tanks per fuel type"). **This is a match, not a gap** — the schema already
supports "MS" as one `Fuel` row with two `Tank` rows under it (one per stream), same for
"HSD". Nothing needs to change structurally; what's actually missing is *data*, not
*schema* — there's no evidence in the current seed/dev data of tanks actually named/coded
`MS-22`, `MS-16`, `HSD-16`, `HSD-22`, and no field anywhere for the site's own tank code
distinct from the fuel name.

## 2. Daily stock reconciliation, including the Testing row

The Sale Details table is a single cross-product-stream reconciliation:

| Row | Meaning |
|---|---|
| O/S | Opening Stock |
| Purchase | Received that day |
| Shift1 / Shift2 | Litres dispensed, by shift |
| **Testing** | Litres run through a nozzle for dip/calibration checks |
| Total Stock | O/S + Purchase − (Shift1+Shift2) |
| (+/-) | A manual adjustment figure |
| Closing Stock | Total Stock ± adjustment |

**Corrected after this was first published** (see PROJECT_CONTEXT.md's "WRONG TURN,
CORRECTED" entry): the Total Stock row does **not** subtract Testing, and this table
originally said it did. The sheet's own arithmetic settles it —
`35,485 + 23,000 − 8,371 − 8,828 = 41,286`, exactly the sheet's own Total Stock figure,
with Testing's 65 L nowhere in that sum. The domain reason: this pump's calibration
testing dispenses into a measured can through a nozzle and pours the fuel straight back
into the same tank, so it crosses the meter (which is why it's tracked at all) but never
actually leaves tank stock.

**How this repo models it:** `app/models/fuel_reconciliation.py` (`FuelReconciliation`)
has `opening_stock`, `received_quantity`, `sold_quantity`, `internal_consumption_quantity`,
`expected_closing_stock`, `physical_stock`, and `variance` (the `physical_stock`/`variance`
pair *is* this report's `(+/-)` concept, just named and signed differently) —
`expected_closing_stock = opening + received − sold − internal_consumption`, matching the
sheet's own Total Stock arithmetic (Testing correctly excluded). `testing_quantity` also
exists on the same record, but purely informationally, matching the sheet's own Testing
row: it never reduces `expected_closing_stock`, sourced from
`NozzleAssignment.testing_volume` (`app/models/nozzle_assignment.py`) rather than any tank
transaction, since testing is something that happens at the nozzle meter, not the tank.
`SaleService.settle_assignment_cash` subtracts that same `testing_volume` before billing
an assignment's remaining dispensed fuel as a cash sale, so test dispenses aren't silently
sold to nobody. The other structural difference from the sheet: this report reconciles
**per fuel stream per day across both shifts in one table**, where `FuelReconciliation` is
written per tank per date already (compatible), but nothing in `app/services/` currently
aggregates two shifts' worth of `NozzleAssignment` meter deltas into one daily total the
way this sheet's Shift1+Shift2 rows do before comparing against Purchase/Closing Stock.

## 3. Per-shift settlement breakdown: CreditSale / CARD / DTP Card / PHONE PAY / PTM / Expenses / Advance / Final

Both Shift 1 and Shift 2 have their own "Transaction Details" table breaking the
shift's total into exactly these eight rows, summing to a shift Total (857,601.467 for
Shift 1, 901,623.2 for Shift 2 — see the flagged discrepancy below).

**How this repo models it:** `app/core/constants.py` (`PaymentMethod`, line 154) defines
exactly **four** methods: `CASH`, `UPI`, `CARD`, `CREDIT`. This is a **real, material
gap**, not just a naming difference:

- `CARD` and `DTP Card` are two separate rows on the real report (and in Shift 1,
  `CARD` is literally 0 while `DTP Card` carries the actual card total) — this app has
  one `CARD` bucket, so it cannot distinguish them even in principle.
- `PHONE PAY` and `PTM` (PhonePe and Paytm) are two separate rows with very different
  totals (19,953 vs 216,980 in Shift 1) — this app has one `UPI` bucket for both.
- `Expenses` appearing *inside* the settlement breakdown, netted against the shift total,
  has a rough analogue: `ShiftReconciliation`'s docstring
  (`app/models/shift_reconciliation.py`, lines 19-24) explicitly says an approved
  expense paid during the shift reduces the expected cash/UPI/card balance for whatever
  method it was paid with — same idea, different shape (computed at reconciliation time,
  not stored as its own settlement row).
- **`Advance` and `Final` have no equivalent at all.** Nothing in `Payment`,
  `ShiftReconciliation`, or `Shift` models a cash advance handed to/from an attendant
  before or after a shift. (See Open Questions — what these actually represent needs
  confirming before modeling them.)
- `CreditSale` as a settlement-breakdown row *is* covered by this app's own `CREDIT`
  payment method plus `Sale`/`CreditAccount`, just organized differently: here it's one
  row in a flat shift total; in this app it's the sum of individual `Sale` rows with
  `payment_method="credit"`, reachable via `SaleService`/`CreditService`.

## 4. Two per-shift cash books, with bank deposits and cash-in-hand carry-forward

Each shift has its own "Cash Book" — a literal T-account: Cash Receipt side (Opening
Balance, Advance, Final) against Cash Payment side (one or more named bank-deposit lines,
e.g. "Sopankaka Bank", plus a residual "Cash in hand" line), both sides summing to the
same total. Critically, **Shift 2's Opening Balance (29,435.00) is exactly Shift 1's
closing "Cash in hand" (29,435.00)** — this is an explicit cash carry-forward chain
between shifts, and Shift 2's cash book also has a named variance-recovery line ("cash
Short Retrun ( Pramod Soni )", 416.00 — cash a named attendant is returning to cover a
prior shortage).

**How this repo models it: not modeled at all.** There is no cash-book/ledger entity
anywhere in `app/models/` — no opening/closing cash-on-hand field on `Shift`, no bank
deposit record, and nothing that carries a balance from one shift's close into the next
shift's open. `ShiftReconciliation` (`app/models/shift_reconciliation.py`) is the closest
existing concept but is architecturally a **snapshot comparison** (expected vs declared,
computed once at close, never edited — line 17: "one reconciliation per shift, never
edited once performed"), not a running ledger with dated line items and a carried
balance. The named-attendant cash-shortage recovery ("Pramod Soni" returning 416) has no
home at all — there's no attendant-attributed shortage-recovery concept anywhere in
`ShiftReconciliation` or `AuditLogRepository`.

## 5. Itemised credit sales with bill series

Each shift's Credit Sale table lists individual bills: a sequential `Bill No` (10292→
10298 for Shift 1, continuing 10299→10301 for Shift 2 — one running series across both
shifts, not reset per shift), a customer `Name`, and an `Amount`, summing to that shift's
`CreditSale` figure from section 3.

**How this repo models it:** matches well. `app/models/sale.py`'s `Sale` rows with
`payment_method="credit"`, linked to `Customer` (`app/models/customer.py`) and gated
through `CreditAccount` (`app/models/credit_account.py`, lines 11-29 — "a Customer with
no CreditAccount cannot be sold to on CREDIT"), already capture "customer, amount,
which shift" per credit transaction. **One real gap**: nothing in this app generates or
displays a human-facing sequential bill number the way `10292`, `10293`... is used here
— `Sale.id` is a UUID (per this project's own "always use UUID primary keys" rule), not
a printable sequential series a customer's paperwork could reference. Two of the seven
Shift 1 credit-sale rows are also "Stock Transfer ( Bouser )" entries (491,396.5 and, in
Shift 2, 579,616) rather than an actual customer sale — see the Bowser Van section below,
since that's the same figure appearing in that section's own ledger.

## 6. Itemised expenses

A flat Expenses Details table: `Details` (a free-text description, often naming a
person, vehicle registration, or vendor — "Diesel Exp (MH12VVX5868)40Lit", "Cash Short
(Harshita)") and `Amount`, summing to 7,433 — which is exactly Shift 1's `Expenses` row
from section 3 (verified: 150+3929+557+1964+510+135+60+68+60 = 7,433 exactly).

**How this repo models it:** matches well, structurally. `app/models/expense.py`'s
`Expense` (lines 26-73) already has `amount`, `expense_date`, `payment_method`,
`description`, `employee_id`, and `shift_id`, plus an approval workflow
(`status`/`approved_by_id`) this paper report has no equivalent of at all. **One
notable pattern difference**: several line items here are themselves *cash-shortage
write-offs attributed to a named person* ("Cash Short (Harshita)", "Cash Short (Almas)")
folded into the same flat expense list as genuine spending (tea, diesel for a vehicle).
This app's `Expense` has an `ExpenseCategory` foreign key (line 47) that could
distinguish "genuine expense" from "shortage write-off" if a category existed for the
latter, but nothing in the current seed data suggests one does.

**Updated since this section was first written**: the "Diesel Exp (MH12VVX5868)40Lit"
kind of line item — fuel drawn from a tank for the pump's own vehicle/generator rather
than genuine external spending — is now modeled. `Expense` gained nullable `tank_id`/
`quantity` columns (enforced together by a database CHECK constraint); when set,
`ExpenseService.create_expense` posts the draw through `TankService.
record_transaction_as_related_action` as an `INTERNAL_CONSUMPTION` transaction, atomically
with the expense row. See open question 10 above for the one thing this still doesn't
resolve: whether these fills cross a nozzle meter the way Testing does.

## 7. Oil Sale ledger

A five-row table (`Name`, `Opening`, `Purchase`, `Salc` [sale count], `Balance`, `Rate`,
`Total`, `Shift`) for five specific lubricant products (Racer 2T 40ml, HP Racer
4-in-1 1ltr, HP Racer 2T 500ml, Milcy Turbo 5ltr, HP Milcy Turbo 1ltr). This is not a
minor aside: its `Total` column, split by the `Shift` column, sums to **exactly** the
`Oil` figures in the main Sale Details table — Shift 1's three rows (92+535+230=857)
match the Sale Details table's Shift1 `Oil`=857 exactly, and Shift 2's two rows
(2037+414=2451) match Shift2 `Oil`=2451 exactly. It is opening/purchase/sale/closing-
balance tracked with the same rigor as fuel, and it feeds directly into `Total Sale`.

**How this repo models it: not modeled at all.** There is no lubricant/oil product
model anywhere in `app/models/` (confirmed — `Fuel`, `Tank`, and every sale/inventory
model are fuel-specific; there is no generic "product" or "SKU" concept an oil product
could reuse). See the flagged business-rule conflict below — this is the direct
evidence for it.

## 8. The Bowser Van section (A / B / C)

Three sub-sections on the same sheet:

- **A] internal stock**: an Ltr/Rs table with rows "Internal Stock", "Opening Stock",
  "Stock Transfer", totalling 13,477.25 Ltr / ₹1,324,005.04.
- **B] itemised deliveries**: a `Bill No`/`Cust Name`/`Qty`/`Amount`/`Transport`/`Total`
  table for four customers (Sigma Power Control, Pritam Ganjewar (Dhayri), Duramiix RMC
  LLP, sai redymix concrate (mulkhed)) — bulk diesel deliveries to construction/concrete
  businesses, each carrying its own `Transport` charge on top of the fuel amount, plus a
  "Closing Stock" total row (Qty 5,750 / Amount 564,880 / Transport 1,550 / Total
  566,430).
- **C] meter reading**: `Start Reading` (2,689,651.00) / `Testing` (0.00) / `End Reading`
  (2,695,401.00) on the bowser's own dispensing meter, plus a `Net Sale` label — the
  same opening/closing-meter pattern `NozzleAssignment.opening_meter`/`closing_meter`
  already uses for a fixed nozzle.

This section is not a footnote: the main Credit Sale tables (section 5) tie into it
directly. Shift 1's "Stock Transfer ( Bouser )" credit-sale line (491,396.5) is within
~0.02 of Bowser section A's "Opening Stock" Rs figure (491,396.48), and Shift 2's
"Stock Transfer ( Bouser )" line (579,616) matches Bowser section A's "Stock Transfer"
Rs figure (579,616) **exactly**. So: fuel is drawn from the main tank into the bowser
van (recorded as a credit-sale "stock transfer" against the van itself), the van then
resells it to its own separate customer list with a transport surcharge, and the van's
own meter is read and reconciled the same way a nozzle is.

**How this repo models it: not modeled at all.** There is no mobile-dispensing /
tanker-van concept anywhere in this codebase. `app/models/tank_transaction.py`'s
`TankTransaction` (lines 11-50) has exactly three transaction types
(`app/core/constants.py`'s `TankTransactionType`, line 115: `RECEIPT`, `ISSUE`,
`ADJUSTMENT`, confirmed by grep — no fourth "transfer" type and no "bowser"/"van" string
anywhere in `app/models/` or `app/services/`). A bowser van is, functionally, a second
point of sale with its own meter, its own customer list, and its own stock — closer to a
second `Nozzle`+`Tank` pair than to anything in `TankTransaction`'s current three-value
enum, but that's a design choice for a later step, not this one.

---

## ⚠ Flagged, not resolved: contradicts the recorded "fuel only" business rule

`PROJECT_CONTEXT.md` line 562 records: *"Does the pump need to track anything it sells
other than fuel (lubricants, oils, accessories, shop merchandise)? **Answered by the
owner, 2026-08-18: no.**"* — and the codebase matches that rule faithfully today; there
is genuinely no lubricant/oil model anywhere (section 7 above).

The report directly contradicts this. The Oil Sale ledger is not an incidental scribble
— it is tracked with full opening/purchase/sale/balance/rate rigor, split by shift,
and its totals are load-bearing inputs to the same sheet's headline `Total Sale` figure
(section 1's table adds an `Oil` column into `Total Sale` for both shifts). A report
that treats oil sales as first-class, reconciled revenue is hard to square with "the
pump doesn't sell anything but fuel."

**This document does not change the business rule.** Per this project's own standing
instruction not to invent business rules and to record assumptions rather than resolve
them unilaterally, this conflict is left exactly as found, for the owner to reconcile:
either the 2026-08-18 answer was about a different, narrower scope than what this report
actually shows, or the report reflects real-world practice the original question didn't
anticipate. See Open Question 1.

## ⚠ Flagged, not resolved: Shift 1's 0.227 discrepancy

Shift 1's Transaction Details table (section 3) sums to a `Total` of **857,601.467**.
That figure is independently verifiable and exact: `501,085.467 + 0 + 5,209 + 0 +
19,953 + 216,980 + 7,433 + 67,700 + 39,241 = 857,601.467`, to the last thousandth.
The same shift's `Total Sale` cell in the main Sale Details table (section 2) instead
reads **857,601.24** — a gap of **0.227**.

Working backward: the 3-decimal precision in `857,601.467` isn't a typo — it traces
directly to individual Credit Sale line items in section 5 that are themselves recorded
to 3 decimal places (`1000.083`, `3638.624` — both from Shift 1's Credit Sale table,
and both sum exactly into `CreditSale`'s `501,085.467`). That is itself notable set
against `app/core/money.py`: this project's own rounding policy (`money()`,
`app/core/money.py` lines 53-55) exists specifically to settle a figure to exactly 2
decimal places (paise) via `ROUND_HALF_UP` the moment it becomes a monetary amount,
precisely because — per that file's own docstring (lines 5-8) — multiplying a
3-decimal litre quantity by a 2-decimal rate produces a longer, unsettled result, and
"something has to decide what the two-decimal money value actually is." These two
credit-sale entries read exactly like that unsettled intermediate value (litres × rate,
never quantized to paise) being written straight onto the bill.

That explains why `857,601.467` has a third decimal at all. It does **not** explain the
0.227 gap to `857,601.24`, because no standard rounding of `857,601.467` reaches
`.24`: `money()`'s own `ROUND_HALF_UP` policy would settle it to **857,601.47** (round
the 7 up), and even plain truncation only reaches 857,601.46. `857,601.24` is 0.23 below
the properly-rounded figure and doesn't correspond to any single rounding rule applied
to the same number. The more likely explanation is that `Total Sale` was **not**
derived from the Transaction Details total at all — it reads like an independently
computed or independently entered figure (plausibly from litres-dispensed × rate,
computed and rounded separately per fuel stream, the same "two different unrounded
paths quietly disagree" failure mode `money.py`'s docstring was written to describe) that
happens to land close to, but not on, the transaction-breakdown total for the same
shift.

What this implies for this project: it is a real, physical instance of exactly the bug
class `app/core/money.py` exists to prevent — two numbers that are supposed to represent
"the same shift's total" computed by two different paths, without a single settlement
point, quietly disagreeing by a fraction nobody would notice unless they added the
column by hand. It's independent confirmation that this project's existing "quantize
once, at the point a figure becomes money" discipline is the right one to hold future
report-generation code to — not a defect in `money.py` itself. See Open Question 9.

---

## Open questions for the pump owner

1. `PROJECT_CONTEXT.md` records "fuel only, no lubricants" as confirmed on 2026-08-18,
   but this report's Oil Sale ledger is tracked with the same rigor as fuel and feeds
   directly into `Total Sale`. Was the original question understood narrowly (e.g. "no
   *shop* merchandise") while oil/lubricant sales at the pump counter were always
   assumed in scope? Should the rule be revisited?
2. What do the `-22` and `-16` suffixes in `MS-22`/`MS-16`/`HSD-16`/`HSD-22` denote —
   two different tanks per fuel, two different grades/specs, or something else (e.g. a
   tank capacity in kilolitres, or a nozzle/pump number)?
3. What is `DTP Card`, and how is it different from the plain `CARD` row it sits next to
   in the same table (a different card network, a different physical terminal, a
   different merchant account)?
4. Is the Bowser Van in scope for this system at all, or is it deliberately run as a
   separate operation whose only touchpoint with the pump is the "Stock Transfer"
   credit-sale line?
5. Are `Advance` and `Final` cash handovers to/from an attendant (e.g. float given at
   shift start, cash collected at shift end), or something else entirely? They appear in
   both the Transaction Details table and the Cash Book, in a way that suggests they're
   the same event viewed from two tables, but that's this document's inference, not
   something stated on the sheet.
6. When a cash shortage is attributed to a named attendant (e.g. "Cash Short (Harshita)"
   in Expenses, or Shift 2's cash book entry "cash Short Retrun ( Pramod Soni )"), how is
   it actually recovered in practice — payroll deduction, a running personal ledger,
   an immediate cash handover like the Shift 2 entry shows? Is there ever a case where it
   isn't recovered?
7. Is the `Bill No` series for credit sales (10292, 10293, ...) shared across every
   shift/day pump-wide, or does it reset on some schedule (daily/monthly)?
8. Section 8's Bowser meter reading includes a `Testing` row reading `0.00` — is that
   the same kind of dip/quality-testing draw as the main Sale Details table's `Testing`
   row, just usually zero for the van specifically?
9. Were Shift 1's `Total` (857,601.467, from the Transaction Details breakdown) and
   `Total Sale` (857,601.24, in the main Sale Details table) ever meant to be the exact
   same figure computed two different ways, or are they understood internally as two
   genuinely different numbers (e.g. one includes something the other excludes)?
10. When the genset, the Omni, or a company vehicle is filled from a tank (the
    internal-consumption expenses in section 6), does that fuel pass through a nozzle's
    meter the same way a calibration test does, or through a separate hand-pump/dip-and-
    pour path that never touches a nozzle meter? This matters directly: if it crosses a
    nozzle meter, it has the same double-count risk Testing did before this document's
    correction (the litres would need excluding from that nozzle assignment's billed cash
    sale, the same way `testing_volume` now is) and today's implementation
    (`TankTransactionType.INTERNAL_CONSUMPTION`, no meter involvement) would need the same
    fix applied to it. This isn't guessable from the report or the codebase and needs the
    owner to describe how these fills are actually done at this pump.
