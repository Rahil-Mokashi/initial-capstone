# Petrol Pump ERP — First Shift Runbook

For the person setting the system up and sitting with it through its first
real shift. Work top to bottom. Nothing here is optional the first time.

The order matters: several steps are blocked until an earlier one is done,
and that is deliberate rather than a defect — the system refuses to record
data it knows is wrong instead of accepting it and corrupting everything
downstream.

---

## Before the shift starts (allow one hour)

### 1. Install and sign in

Run the installer, launch the app, and sign in with:

- **Username:** `admin`
- **Password:** `Admin@123`

You will be **forced to change the password immediately** — this is not
skippable, because the default is publicly known. Choose one you will
still have during the shift and **write it down somewhere safe now**.
There is no self-service recovery; only another administrator account can
reset it.

### 2. Set fuel prices — nothing works until you do

Open **Fuel Prices** and set a real rate for Petrol, Diesel and Power.

They ship at **0.00**, and the system **refuses to record a sale of an
unpriced fuel**. This is intentional: a sale booked at 0.00 would silently
falsify revenue, credit balances, reconciliation and every report. If you
skip this step, every sale attempt during the shift will fail.

Prices are versioned — each change records who made it and when, so you
can raise them mid-shift if the depot price moves.

### 3. Enter the physical site

In this order, because each depends on the last:

1. **Tanks** — code, fuel type, capacity, and **current stock as it
   actually is right now**. This opening figure is what every future
   reconciliation measures against, so dip the tanks and enter the real
   number, not an estimate.
2. **Dispensers**, then **Nozzles** on them. Each dispenser takes exactly
   two nozzles. If a fuel has more than one tank, set each nozzle's tank
   so the system knows which one it draws down.
3. **Employees** — everyone working the shift.
4. **Users** — a login for anyone who needs one. Give attendants their own
   accounts; do not let people share one, or the audit trail records the
   wrong person.

### 4. Enter credit customers

For each regular credit customer: create the **customer**, then open a
**credit account** with their limit and payment terms.

Both steps are required. A customer without a credit account **cannot be
sold to on credit at all** — opting in is deliberate. If they already owe
you money, record that as an opening credit sale so the balance is right.

### 5. Take a backup and copy it off the machine

Open **Backups**, take one manually, then use **Copy to USB / Network** to
put a copy on a USB stick. Do this *before* the shift, so you have a clean
starting point to return to if the day goes badly.

---

## During the shift

### Opening

1. A supervisor opens the **shift**.
2. Assign each attendant to a nozzle, entering the **opening meter
   reading** from the dispenser face.

An attendant cannot record sales until they are assigned to a nozzle in an
open shift. Their **My Shift** screen shows what they are on.

### Recording sales

Attendants see a simplified form — their own assignment is filled in
automatically, so they only enter quantity and payment method.

- **Credit** sales require a customer with an account and available limit.
  A sale that would breach the limit is refused outright, not warned about.
- UPI and card sales have a reference field for the transaction ID or
  authorisation code. Use it; reconciliation is far easier with it.

### If something is wrong

**Do not delete or re-enter anything.** Use **Cancel Sale**, which needs a
reason, returns the fuel to the tank and reverses the payment — leaving
the original, the reversal and the reason all on record. Re-entering data
to "fix" a number is the one habit that will make the books untrustworthy.

### Closing

1. Complete each nozzle assignment with its **closing meter reading**.
2. Close the shift.
3. Run **Reconciliation**: count the cash, read the UPI and card totals,
   and enter what you actually have. The system compares it against what
   it expected.

**A variance is not an accusation.** Small ones are normal and are simply
recorded. Large ones are flagged for a manager to approve. Nobody is
required to explain a rounding difference.

### End of shift

1. Open **Reports → Daily Summary** and check it against your own count.
2. Take a **backup** and **copy it to the USB stick again**.

---

## Things that look like faults but are not

| What you see | What is actually happening |
|---|---|
| Every sale is refused | Fuel prices are still 0.00 — set them in **Fuel Prices** |
| A credit sale is refused | Customer has no credit account, or the sale would exceed their limit |
| Attendant sees almost nothing | Correct — attendants see only their own shift and sales |
| **Alerts** shows no number for the first minute | The count refreshes about once a minute; opening the screen recalculates immediately |
| Account locked after wrong passwords | Locks for 15 minutes, then unlocks itself. An admin can clear it sooner |
| Shift will not close | An assignment is still active — complete or cancel it first |
| Nozzle cannot be deactivated | It is assigned in an open shift |

---

## What to write down during the shift

This first shift is worth more as evidence than as data entry. Keep a
notebook and record:

- **Any figure the system reports that disagrees with your own count**,
  and what each said. This is the single most valuable thing you can
  collect.
- **Anywhere someone hesitated or asked what to do.** Confusion is a
  design problem, not a user problem.
- **Anything that felt slow** during a busy period, and roughly how long
  it took.
- **Anything you wanted to record and could not.**

Bring that back and it turns into the next round of work. The software has
been tested extensively against how a petrol pump is *specified* to
operate; this shift is the first test against how yours *actually* does,
and where those differ, the software is what changes.

---

## If something goes seriously wrong

- **The app will not start, or data looks corrupted** — stop, do not
  re-enter anything, and follow `recovery-guide.md`. There is a backup
  from before the shift.
- **The computer loses power mid-sale** — restart the app and check the
  last sale is present. The database is designed to survive this: a
  transaction either completed or did not, never half.
- **You are unsure whether something saved** — check the relevant list
  screen rather than entering it again. A duplicate is harder to unpick
  than a missing record.

Keep the pre-shift USB backup until you are satisfied the day's data is
sound.
