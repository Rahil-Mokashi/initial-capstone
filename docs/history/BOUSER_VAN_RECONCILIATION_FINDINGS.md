# Bouser Van Reconciliation — Findings

**Type:** Read-only investigation. No code, docs, or data modified. Answers the AMBIGUOUS relationship graphify's knowledge-graph audit flagged between the ₹5,66,430 Bouser Van billing total and the "Net Sale" 5,750 meter figure.

## What the two figures actually represent

Both figures come from the same source: a single handwritten petrol-pump daily report sheet, photographed and kept as reference material at `docs/reference/WhatsApp Image 2026-09-14 at 19.00.37.jpeg`. That photo is analyzed in detail in `docs/daily-report-spec.md` section 8, "The Bowser Van section (A / B / C)" (`docs/daily-report-spec.md:207-241`). It is **not** app data — nothing in this repo's database, models, or services currently represents a Bowser Van (confirmed below).

- **Section B — itemised deliveries** (`docs/daily-report-spec.md:213-218`): a `Bill No / Cust Name / Qty / Amount / Transport / Total` table for four bulk-diesel customers, with a "Closing Stock" total row reading **Qty 5,750 / Amount 564,880 / Transport 1,550 / Total 566,430**. `Qty` is a volume in litres; `Amount`, `Transport`, and `Total` are all in rupees. `Total = Amount + Transport` (564,880 + 1,550 = 566,430 — exact).
- **Section C — meter reading** (`docs/daily-report-spec.md:219-222`): `Start Reading` 2,689,651.00 → `End Reading` 2,695,401.00 on the bowser van's own dispensing meter, labeled `Net Sale`. The meter difference is 2,695,401.00 − 2,689,651.00 = **5,750** — a litre figure, using the exact same opening/closing-meter pattern `NozzleAssignment.opening_meter`/`closing_meter` already uses for a fixed nozzle.

## Were they ever supposed to reconcile with each other?

**Yes — and they do, exactly.** The investigation's step 1 (confirm units) is the whole answer: the ₹5,66,430 figure the task description names is the **Total** column (rupees), while the 5,750 figure is being compared against the wrong pair. The two numbers that were actually meant to reconcile are:

- Section B's **Qty** total: **5,750 litres**
- Section C's **Net Sale** (meter difference): **5,750 litres**

These match **exactly** — the bowser van's own meter confirms it dispensed the same 5,750 litres that Section B's billing table charged four customers for. ₹5,66,430 is simply the rupee total for that same 5,750 litres (564,880 for the fuel itself, plus a 1,550 transport surcharge) — it was never supposed to equal a litre figure at all. Comparing ₹5,66,430 against 5,750 is comparing a currency total against a volume, which is exactly the "units were never supposed to match" case the investigation brief flagged as a likely full explanation on its own — and here it is confirmed, not just plausible, because the correctly-paired litre figures (Qty vs. Net Sale) match to the last unit.

This also isn't an isolated coincidence — the same sheet's numbers cross-check independently elsewhere: Shift 1's "Stock Transfer ( Bouser )" credit-sale line (491,396.5) is within ~0.02 of Section A's own "Opening Stock" rupee figure (491,396.48), and Shift 2's "Stock Transfer ( Bouser )" line (579,616) matches Section A's "Stock Transfer" rupee figure **exactly** (`docs/daily-report-spec.md:224-231`). The whole Bowser Van subsystem on this one handwritten sheet is internally consistent.

## Why graphify's audit flagged it as AMBIGUOUS instead of resolving it

The extraction subagent that processed this image (chunk 5 of the `/graphify` run) recorded the numbers correctly but did not do the arithmetic to notice `2,695,401.00 − 2,689,651.00 = 5,750` matches Section B's Qty column, nor that `564,880 + 1,550 = 566,430`. It flagged a `RECONCILES_WITH` edge between "Section B: Bouser Van customer bills" and "Net Sale figure" as AMBIGUOUS specifically because it could see the two sections were related but wasn't confident *which* numbers within them corresponded — a subtraction and an addition it never performed. This finding closes that gap: the relationship is confirmed EXTRACTED-grade (arithmetic identity), not merely inferred.

## Is this a data-entry error, a missing system link, or a real bug?

**None of the three — because there is nothing to be a bug in.** Point 3 and 4 of the investigation brief asked whether Bowser Van sales flow through a modeled billing/metering path in this codebase, and whether a class of bug comparable to the earlier TESTING-volume double-count could exist here. Checked directly:

- `grep -ri "bowser\|bouser\|van" app/models/ app/services/` returns **nothing**. There is no Bowser Van model, no dedicated transaction type, no service method anywhere in the running application.
- `app/models/tank_transaction.py`'s `TankTransaction` (lines 11–50) and `app/core/constants.py`'s `TankTransactionType` (line 115) define exactly three transaction types — `RECEIPT`, `ISSUE`, `ADJUSTMENT` — confirmed by grep to be the complete set. There is no fourth "transfer" type a bowser van's internal stock movement (Section A) would use.
- This is explicitly recorded already in `docs/daily-report-spec.md:233-241`: *"How this repo models it: not modeled at all... A bowser van is, functionally, a second point of sale with its own meter, its own customer list, and its own stock — closer to a second Nozzle+Tank pair than to anything in TankTransaction's current three-value enum, but that's a design choice for a later step, not this one."*

The earlier TESTING-volume bug (migrations `ddb899222f7c` adding `nozzle_assignments.testing_volume`, and `85b6bbb9cace` adding `internal_consumption_volume`, both referenced in `PROJECT_CONTEXT.md` around lines 805–863) was a real code bug *because testing volume tracking was actually implemented* in `NozzleAssignment`/`TankService` — the meter difference included testing litres that were never subtracted from expected closing stock, so reconciliation overcounted real sales. That bug class requires the feature to exist in code first. The Bowser Van has no code path at all to have that bug in — it exists only as a photographed paper form kept for reference. So this is not a data-entry error (the numbers on the sheet are internally consistent) and not a missing link between two systems in the sense of a wiring bug (there is only one "system": a piece of paper) — it is, at most, a **feature that has never been built**, which `docs/daily-report-spec.md` already tracks as its own open question (see below), separate from this reconciliation question.

## Exact sources, for independent verification

| Figure | Value | Source |
|---|---|---|
| Section B Qty (total row) | 5,750 (litres) | `docs/daily-report-spec.md:217` — describing `docs/reference/WhatsApp Image 2026-09-14 at 19.00.37.jpeg` |
| Section B Amount (total row) | ₹564,880 | `docs/daily-report-spec.md:217-218` |
| Section B Transport (total row) | ₹1,550 | `docs/daily-report-spec.md:218` |
| Section B Total (total row) | ₹566,430 | `docs/daily-report-spec.md:218` (564,880 + 1,550 = 566,430) |
| Section C Start Reading | 2,689,651.00 | `docs/daily-report-spec.md:219` |
| Section C End Reading | 2,695,401.00 | `docs/daily-report-spec.md:219-220` |
| Section C Net Sale (derived) | 5,750 (litres) | this document — 2,695,401.00 − 2,689,651.00, confirmed against `docs/daily-report-spec.md:219-222` |
| Section A Opening Stock (Rs) | ₹491,396.48 | `docs/daily-report-spec.md:225-226` |
| Section A Stock Transfer (Rs) | ₹579,616 | `docs/daily-report-spec.md:226-227` |
| "Bowser Van not modeled in code" confirmation | — | `app/models/tank_transaction.py:11-50`, `app/core/constants.py:115`, cross-checked by grep across `app/models/` and `app/services/`; independently documented at `docs/daily-report-spec.md:233-241` |
| TESTING-volume precedent (real code bug, different situation) | — | `PROJECT_CONTEXT.md:805-863`, migrations `ddb899222f7c` and `85b6bbb9cace` |

## What could not be resolved with certainty — flagged for the pump owner, not guessed at

`docs/daily-report-spec.md` already logs two open questions directly relevant to this exact section, which this investigation does not attempt to answer since they require knowing how Bowser Van operations actually work at this specific pump, not just what the numbers say:

1. **(Existing open question 4, `docs/daily-report-spec.md:323-325`)** Is the Bowser Van in scope for this system at all, or is it deliberately run as a separate operation whose only touchpoint with the main pump system is the "Stock Transfer" credit-sale line? This determines whether the "feature that's never been built" gap above is worth building at all.
2. **(Existing open question 8, `docs/daily-report-spec.md:338-340`)** Section C's meter reading includes a `Testing` row reading `0.00` — is that the same kind of dip/quality-testing draw the main Sale Details table's `Testing` row represents (i.e., would a non-zero value here need the same carve-out treatment `NozzleAssignment.testing_volume` got after the earlier bug), just usually zero for the van specifically?

Both remain genuinely open. This investigation adds no new open question of its own — the reconciliation itself is fully explained by the unit mismatch identified above, with no residual uncertainty in the arithmetic.
