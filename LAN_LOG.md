# LAN multi-user build log

Start: 2026-10-13 09:25 IST. Branch `feature/lan-multi-user` (never pushed).

## Phase 0 - preflight (elapsed 0:00)
- TWELVE_HOUR_REPORT.md exists and is committed (`d17a399`). Tree clean; PROMPT_LAN.md / run_prompt.ps1 / private_samples/ not present on this machine, ignore entries added anyway.
- Baseline on HEAD `d17a399`: Python 1804 passed, 1 skipped; web Vitest 360; desktop Vitest 33; Playwright 53 passed, 9 opt-in skipped.

## Phase 1 and 2 - modes, Main PC server, enrolment, Client PC (09:30 - 10:35, about 1h05)
Commit: one combined commit (see below): the pieces share files (`api/app.py`, `api/services.py`, `web/src/api/openapi.json`), so splitting them would have left commits that do not run.
- ADR `docs/adr-lan-multi-user.md` (committed on its own).
- `api/lan/`: `config.py` (lan.json; no file = Single PC; unreadable file is NOT treated as Single PC), `pki.py` (own CA, server certificate, per-device client certificates, revocation list; keys are PEM encrypted with a DPAPI-protected passphrase), `dpapi.py` (ctypes, machine scope), `fs_security.py` (icacls: SYSTEM, Administrators and the running account only; verified, refuses if it cannot), `devices.py` (pairing code: 10 characters, single use, 10 minutes, 5 wrong tries; HMAC proof over the authority fingerprint with PBKDF2; device token stored as a hash), `guard.py` (network allow-list, Host check, size limit, device token, per-device and sign-in rate limits, request time limit), `server.py` (`run_main` refuses to start unless every protection is in place; the enrolment listener exists only while a code is live), `writelock.py` (one writer at a time; the audit chain stays one line), `cli.py` (`lan init / status / enrol-local / run`).
- A real bug found by the tests: enrolment first trusted the fingerprint the CALLER claimed, so a machine in the middle could have passed; it now uses the Main PC's own. Second: SQLAlchemy's `commit` event fires BEFORE the driver commits, so a lock released there let the next writer read the old newest audit row and fork the chain; the lock is now released after the real commit, and taken before `AuditLogRepository.record` stamps its time (otherwise the chain is intact by hash but out of time order, which `verify_chain` rejects).
- Existing tables/models: one new table `lan_devices` (migration `ce8b95164556`), one new permission `device.manage` (owners/admins only, like every new permission).
- Single PC mode is unchanged: no `lan.json` = the old path; `/api/devices` answers 404 there; `api/main.py` refuses Single PC mode on a PC that is installed as the Main PC (two programs writing to one database would break the audit chain).
- Desktop: `lan-client.ts` (pairing, device file, safeStorage-held key, loopback proxy that pins the authority and adds the device identity), Network setup window (`setup.html`, `preload-setup.ts`; IPC only from that window), main-process wiring. The window still talks only to `http://127.0.0.1:<port>`, so the strict CSP, the request blocker and the offline build check are unchanged.
- Web: Devices screen (owner), Network setup link on the sign-in page, "From PC" column in the Audit Log.
- Scripts: `scripts/lan/firewall-main-pc.ps1`, `install-main-pc.ps1` (both with `-DryRun`; tested; NOT run for real: that needs an elevated PowerShell on a Main PC).
- Tests: 54 Python (`tests/api/lan/`), 13 Node (`desktop/src/lan-client.test.ts`, real TLS against the test Main PC), 5 web, 3 Playwright (two Client PCs against one Main PC: pairing through the setup window, a device file, live shared data, removing a device, the Main PC going away).
- UI/UX review (screenshots in `docs/screenshots/lan/`): the top bar still said "Offline - Local Only" on a Client PC; replaced by a connection light. A removed PC got raw JSON on reload; it now gets a plain page. Done is not the same as Cancel on the pairing dialog (Done keeps the code alive).
- Full suites: `tests/api` + `tests/site` 857 passed; web 372 passed.

## Owner's mid-run request (10:10): one screen to close a shift
The owner asked for one place to type the closing master readings and how the money was collected, with the tally and any shortage shown at once, and for the software to be easier to go round. Built: `Close Shift` (`app/services/close_desk_service.py`, `api/routers/close_desk.py`, `web/src/features/close-shift/`).
- The tally is the owner's own report formula (`Credit sales + CARD + DTP Card + Other + PHONE PAY + PTM + Expenses + Advance + Final = Total Sale`); the difference shows as Balanced / Short / Excess (tolerance one paisa, as the report's own check).
- A preview runs the very same writes inside one transaction and rolls them ALL back, so the figures shown while typing cannot differ from what is saved. Saving is all-or-nothing (readings, totals and cash in one unit of work); tested.
- Opening reading = the nozzle's last closing (already so; typed only the first time a nozzle is ever used). Testing: usual 5 litres pre-filled per nozzle (new Owner Choice `default_testing_litres`, T-15); it stays out of the litres sold and out of the tank's decrease.
- Advance and Final are written once per shift (existing rule); after saving they are shown, not typed. Card/Phone Pay totals can be retyped (the old one is voided with a reason, as today).
- Menu: the cashier sees one `Close Shift` entry instead of three; Today's list for the cashier is shorter. `docs/SOFTWARE_MAP.md` explains the screens by rhythm (every shift / every day / now and then) and where each kind of change lives in the code.
- NEEDS HUMAN REVIEW: shortage cannot be pinned on a person (nobody is named per nozzle); T-15 default of 5 litres is the owner's statement, to be confirmed.
