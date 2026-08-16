# Petrol Pump ERP — Administrator Guide

This guide covers installing, configuring, and administering the app — setting up users and roles, adjusting settings, and understanding where its data lives. For day-to-day operation, see `user-guide.md`. For backup and disaster recovery, see `recovery-guide.md`.

## Installation

Run the installer and follow the prompts. It installs the application and creates Start Menu shortcuts to the app and to this documentation. No separate Python installation or other runtime is required — everything needed is bundled.

The app is entirely offline: it has no network dependency, does not phone home, and does not require an internet connection to run. All data stays on the machine it's installed on.

## First login

The very first time the app runs, it creates a default administrator account:

- **Username:** `admin`
- **Password:** `Admin@123`

You will be forced to change this password on first login — choose something the default account holder alone knows, then use that account to create real named accounts for your actual staff. Don't keep using the shared `admin` login day-to-day; give each person their own account so the audit trail (see below) reflects who actually did what.

## User management and roles

Open **User Management** (Admin/Owner only) to create accounts and assign roles. The available roles are:

| Role | Typical use |
|---|---|
| Admin | Full system access, including user management and configuration |
| Owner | Full operational access, same practical scope as Admin today |
| Manager | Runs day-to-day operations: employees, procurement, expenses, reports, approvals |
| Accountant | Payments, credit accounts, expenses, financial reports |
| Shift Supervisor | Opens/closes shifts, assigns nozzles, performs reconciliation |
| Attendant | Records sales on their assigned nozzle, views their own attendance/shift history |

Every action a user takes that matters financially or affects another user's access is written to the audit log automatically — there is no separate step to enable this. Open **Audit Log** (Admin/Owner) to review who did what and when.

### Password and session policy
- Passwords require at least 8 characters, an uppercase letter, a lowercase letter, and a digit.
- An account locks automatically after 5 failed login attempts.
- Sessions expire after inactivity (default 8 hours — configurable, see below).

## Where the app's data lives

The app stores everything in a per-user folder so it survives updates and reinstalls:

```
%LOCALAPPDATA%\PetrolPumpERP\
  petrol_pump.db          the database (SQLite)
  petrol_pump_erp.log      application log (rotates automatically)
  backups\                 database backups
  reports\                 default location report/receipt exports save to
  config.env                optional configuration overrides (see below)
```

## Configuration

Most behavior works out of the box with sensible defaults. To change a setting without reinstalling, create (or edit) `config.env` in the folder above, with lines like:

```
SESSION_TIMEOUT_HOURS=12
AUTO_BACKUP_INTERVAL_HOURS=12
LOG_LEVEL=INFO
```

| Setting | Default | What it controls |
|---|---|---|
| `SESSION_TIMEOUT_HOURS` | 8 | How long an inactive session stays logged in before requiring sign-in again |
| `AUTO_BACKUP_INTERVAL_HOURS` | 24 | How often an automatic backup is taken (on startup, if the most recent one is older than this) |
| `LOG_LEVEL` | INFO | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

Changes take effect the next time the app starts. A real environment variable of the same name always overrides the file, if you ever need to set one for a specific launch.

## Backups

The app takes a backup automatically:
- Before applying any database schema update
- Once a day during normal use (configurable above)

You can also trigger one manually, and check database integrity on demand, from the **Backup & Restore** screen. See `recovery-guide.md` for how to restore from one.

## Reports and permissions

Every report is gated by a permission tied to the relevant role — a Manager sees Business Insights and procurement reports, an Accountant sees financial ones, and so on. If a role needs access to a report it currently doesn't have, that's a role/permission assignment to review in User Management, not something to work around.
