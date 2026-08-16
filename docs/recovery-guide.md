# Petrol Pump ERP — Backup & Recovery Guide

This guide covers what to do if the app won't start, its data looks wrong, or you need to restore from a backup. For normal setup and configuration, see `administrator-guide.md`.

## Where backups live

Every backup is a complete, self-contained copy of the database file, stored at:

```
%LOCALAPPDATA%\PetrolPumpERP\backups\
```

The app takes one automatically before applying any database update, and once a day during normal use (see `administrator-guide.md` for the configurable interval). You can also trigger one manually at any time from **Backup & Restore** — do this before any risky change (a bulk data correction, a manual database edit, handing the machine off for maintenance).

## Checking database integrity

From **Backup & Restore**, use **Check Integrity** to run a full consistency check against the live database. This is safe to run at any time and doesn't change any data — use it if the app is behaving strangely (unexpected errors, numbers that don't add up) to rule out file-level corruption before looking elsewhere.

## Restoring from a backup

1. Open **Backup & Restore** (requires the backup-management permission — Admin/Owner/Manager by default).
2. Select the backup you want to restore from the list, which shows when each one was taken and why (manual, scheduled, or pre-migration).
3. Enter a reason for the restore — this is required and is written to the audit log, since restoring replaces the live database.
4. Confirm. The app automatically takes one more safety backup of the *current* database immediately before restoring, so even a restore chosen in error is itself recoverable.

Restoring requires closing and reopening the app afterward so every open screen reloads against the restored data.

## If the app won't start at all

1. Check `%LOCALAPPDATA%\PetrolPumpERP\petrol_pump_erp.log` for the error — it's a plain rotating text log, safe to open in any text editor.
2. If the log points to a corrupted database file, don't delete it — rename it aside (e.g. `petrol_pump.db.broken`) and copy the most recent file from the `backups` folder into its place as `petrol_pump.db`, then relaunch.
3. If nothing in `backups` is usable either, keep the broken file and the log rather than discarding them — they're what a deeper investigation would need.

## What "never delete, only correct" means for recovery

The app deliberately never deletes or silently overwrites historical financial records — corrections happen through voiding, reversing, or adjusting an entry, all of which stay visible in the record and the audit log. This means that in the vast majority of cases, a "wrong-looking" number is not data corruption at all, but a transaction that needs a correcting action (a reversal, an adjustment) rather than a restore. Reach for a backup restore only when the data itself is actually damaged or lost — for everyday mistakes, use the correction actions built into each module instead, since a restore rolls back *everything* since that backup was taken, not just the one entry that was wrong.
