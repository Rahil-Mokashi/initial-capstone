# Petrol Pump ERP — User Guide

This guide is for day-to-day staff: attendants, shift supervisors, managers, and accountants using the app to run daily operations. For installation, user setup, and configuration, see `administrator-guide.md`. If something looks wrong with the data or the app won't start, see `recovery-guide.md`.

## Signing in

1. Launch **Petrol Pump ERP** from the Start Menu or desktop shortcut.
2. Enter the username and password given to you by your administrator.
3. On your very first login, you'll be asked to set a new password. Choose one that's at least 8 characters, with an uppercase letter, a lowercase letter, and a digit.
4. If you enter the wrong password five times in a row, the account locks for safety — ask your administrator to unlock it.

Sessions expire automatically after a period of inactivity (8 hours by default). You'll be returned to the login screen and simply need to sign in again — nothing in progress is lost, since sales and shift actions are saved as you go, not only at the end.

## What you can see depends on your role

The app shows only the sections relevant to your role. A few examples:

- **Attendant**: your assigned nozzle, recording sales during your shift, your own attendance and shift history.
- **Shift Supervisor**: opening/closing shifts, assigning attendants to nozzles, performing shift reconciliation.
- **Manager**: everything supervisors can do, plus employee records, procurement, expense approval, and reports.
- **Accountant**: payments, credit accounts, expenses, and financial reports.
- **Owner/Admin**: full access, including user management and system configuration.

If a screen or button you expect to see is missing, it's most likely a permissions setting — ask your administrator, don't try to work around it.

## Daily workflow

### Starting a shift
A supervisor opens a shift and assigns attendants to specific nozzles. Each attendant sees their assignment as soon as they log in.

### Recording a sale
From the Sales screen, select the fuel and enter the quantity or amount — the price is locked in at the moment of sale, so later price changes never alter a receipt that's already been issued. Choose the payment method (cash, UPI, card, or credit for registered customers with an account) and complete the sale. You can print, preview, or export a PDF receipt from the sale record afterward.

### Handling credit sales
Credit sales are only available for customers with a registered credit account and available credit limit. The app checks the limit automatically — if a sale would exceed it, it will tell you rather than let the transaction through.

### Closing a shift
At shift end, the supervisor closes it and performs reconciliation: expected cash/UPI/card totals (calculated from recorded sales) are compared against what was actually counted. Small variances are flagged for visibility; larger ones require a manager's review and approval before the shift is finalized. Nothing about a closed shift is ever silently edited — corrections go through an adjustment or reversal, never a direct edit, so the historical record stays intact.

### Attendance
Attendants can view and confirm their own attendance and shift history. Managers and supervisors mark attendance for the team.

## Alerts

The **Alerts** button in the top bar shows how many things currently need attention, and turns amber or red when any of them do. Open it for the full list. Alerts cover low fuel, fuel and cash variances, payment mismatches, unmarked attendance, items waiting for your approval, overdue customers, supplier invoices past their due date, missing backups, and database problems.

Two things are worth knowing about how this screen behaves:

- **You only see alerts for the parts of the app you have access to.** Anything waiting for an approval only reaches people who can actually give that approval.
- **There is no "dismiss" button, and this is deliberate.** Every alert is worked out fresh from the current state of the business each time the screen refreshes, so an alert disappears by itself the moment the situation behind it is dealt with — refill the tank, approve the expense, record the customer's payment. Nothing here can be hidden while it is still true, which means an empty Alerts screen genuinely means nothing is outstanding.

The count refreshes on its own about once a minute, so it may be blank for a short while just after you sign in. Opening the screen always recalculates it immediately.

If the list cannot be worked out for some reason, the screen says so explicitly rather than showing an empty list — an empty screen always means "nothing wrong", never "could not check".

## Reports

Open **Reports** from the main menu to generate any report you have access to — sales, payments, credit, expenses, reconciliation, and the Business Insights (performance & forecast) view. Every report supports:

- **Generate** — run it for the date range and filters you choose
- **Print Preview** — see exactly what will print before committing paper
- **Print**
- **Export to PDF**
- **Export to Excel**

Exports default to a `reports` folder kept alongside the app's data, so you can always find what you've saved.

## Getting help

If something in the app looks financially wrong (a total that doesn't add up, a missing transaction), do not try to fix it by re-entering data — flag it to your manager or administrator. The system is deliberately built so that historical financial records are never deleted or silently changed, only voided, reversed, adjusted, or corrected through an approved, audited action. This keeps every number traceable, including the one that looked wrong in the first place.
