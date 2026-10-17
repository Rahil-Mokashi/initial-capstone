# App walk-through, 17 Oct 2026: status of each note

Source: Rahil's audio notes (pasted into the session). P1 = before pilot, P2 = first week, P3 = later.

## Done (branch `feature/pilot-prep`)
- Login: left-side subtext removed (heading kept); bottom-left shows only the device name; Hindi button removed (no language toggle at all); a shown password hides after 3 s. Tests: `web/src/features/shell/login.test.tsx`.
- Top bar: "Offline - Local Only" chip removed on a single PC (Client PC still shows the Main PC link state).
- Company profile: one line says the name and address print on every receipt and report.
- Terminal (office desk, the "pick freely" path): Credit only (Cash/UPI/Card belong to shift-close totals); vehicle number required; "+ New customer" creates the customer (name, phone) and completes the sale. The attendant's own-nozzle path is unchanged.

## Needs an answer before it can be built (defaults NOT assumed)
- DTP and other per-sale methods: `PaymentMethod` is frozen at cash/upi/card/credit (tenders live in a separate table). Which methods besides DTP go through the Terminal (PTM, fleet cards)? Adding one is a model decision.
- The vehicle number is stored in the sale's remarks ("Vehicle: ...") because the sale has no vehicle column; a column needs a migration. Say if you want one.
- Credit limit for a customer made at the counter, and whether an owner approves before the next credit sale.
- Dip chart per tank (cm to litres) for the tank picture.
- Biometric brand and whether it exports attendance (P3).
- User-menu extras (device name and mode, version, switch user, recent activity): which ones.

## Not started
P1: network setup wording; setup guide and user guide documents; app-wide typo-tolerant search; alerts that can be cleared (acknowledge/dismiss with who and when); cash-short alert with the employee and a "mark shortage" button (also on the Today card); digest number overflow; rename/explain "Waiting for you" / "Open review"; simplify the Today page; tank drawing as a horizontal tank; tank names MS-22, MS-16, HSD-16, HSD-22 in seed/demo data; plainer wording on the tank detail page.
P2: polish pass screen by screen; show password rules before Save on Users.
