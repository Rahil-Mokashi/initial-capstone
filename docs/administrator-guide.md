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

---

## Protecting the database file (encryption at rest)

The Petrol Pump ERP database is a single unencrypted SQLite file. Anyone
with access to the PC — or to a stolen drive, or to a backup on a USB
stick — can open it with a free tool and read every sale, salary, customer
balance and supplier price in the business.

**This is a deliberate, recorded decision, not an oversight.** The
reasoning is below so that whoever inherits this system can revisit it
rather than rediscover it.

### Why the database itself is not encrypted

The usual answer is SQLCipher, which encrypts every page of the file
transparently. It was considered and not adopted, because on an
unattended desktop application the key has to come from somewhere:

- **Embedded in the application** — anyone who can read the database can
  also read the executable, so this protects nothing and only creates the
  impression of protection, which is worse.
- **Typed by a person at every startup** — a real improvement, but it
  means the pump cannot open in the morning if the one person who knows
  the passphrase is off sick, and it will be written on a sticky note
  beside the monitor within a week.
- **Held by the operating system** — this is genuinely the right answer,
  and it is exactly what full-disk encryption already provides.

So the protection is delegated to the operating system, where the key
management is already solved properly, rather than reimplemented badly
inside the application.

### What the administrator must actually do

**1. Turn on BitLocker** on the drive holding the application and its
data. On Windows 11 Pro: Settings → Privacy & security → Device
encryption, or Control Panel → BitLocker Drive Encryption. Store the
recovery key somewhere that is not the same machine.

Without this, physical theft of the PC is total data disclosure.

**2. Encrypt the off-device backups too.** A backup copied to a USB stick
leaves the protection of the machine's disk encryption behind. Use a
BitLocker To Go encrypted USB drive, or a network share on an encrypted
server. An unencrypted backup on a lost USB stick is the same disclosure
as a stolen PC, and far likelier.

**3. Use separate Windows accounts** for staff who should not reach the
data directory at all, and keep the database directory readable only by
the account the application runs under.

**4. Do not email or cloud-sync the database file.** It contains
everything, and this application is offline by design precisely so that
the data never leaves the premises unless somebody deliberately moves it.

### What the application does protect

Independently of the file, and regardless of disk encryption:

- Passwords are never stored — only salted, iterated hashes.
- Session tokens are stored hashed, so a stolen database yields no usable
  sessions.
- The audit trail is append-only, enforced by database triggers, and
  chained with hashes so that tampering is detectable even by someone who
  can bypass the triggers.
- Every consequential action requires a reason and records who performed
  it.

Those defend against a dishonest user of the system. Disk encryption is
what defends against someone who takes the disk. Both are needed, and only
one of them can be solved in application code.
