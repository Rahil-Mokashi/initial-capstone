# LAN multi-user build: report

Branch `feature/lan-multi-user` (never pushed). Day-by-day detail and every judgment call: `docs/history/LAN_LOG.md`. Design: `docs/adr-lan-multi-user.md`. Setup: `docs/LAN_SETUP.md`, `docs/MAIN_PC_RUNBOOK.md`. Real-PC checks: `docs/LAN_MANUAL_CHECKLIST.md`.

## What was built
| Phase | Result |
|---|---|
| 1-2 | One Main PC (Python API + the one SQLite database, mutual TLS, per-device tokens, pairing code) and any number of Client PCs (Electron, no local data). Single PC mode is unchanged. A Main PC refuses to start unless every protection is in place; there is no plain-HTTP fallback. |
| Close Shift | One screen for closing readings, how the money was collected, and the tally with Balanced / Short / Excess. The preview runs the real writes and rolls them back. |
| 3 | Live data: events push with a polling fallback, ETag / If-Match version numbers, "Changed by Asha at 14:05" conflict messages, a bigger database pool (80) for many PCs. |
| 4 | Entered, Verified, Approved, Locked chain. A locked shift refuses every write path (`entry_lock_guard`). A correction is an owner's reopen with a reason. |
| 5 | Staff facts report (facts, not a score) and the owner's daily digest with per-owner reviewed marks. |
| 6-7 | Optional daily email summary (off by default, outbound only, password in a DPAPI file), System health screen, scheduled backups with nightly integrity and audit-chain checks, passphrase-encrypted off-device copies, `lan promote` to bring a backup up on a replacement Main PC. |

## Verification (2026-10-15, this working tree)
| Suite | Result |
|---|---|
| Python `tests/api` + `tests/site` | 976 passed |
| Python everything else (Qt UI, services, backup, etc.) | 999 passed, 1 skipped |
| Web: type-check, lint, build with the offline check, Vitest | all clean; 388 passed (50 files) |
| Desktop: type-check, lint, Vitest | all clean; 46 passed |
| Playwright (dev build) | 58 passed, 10 opt-in skipped |
| Packaged installer tests (fresh install of the new installer) | 4 passed (start, run-as-node fuse, inspector fuse, offline rules) |
| Frozen service: `lan init / status / enrol-local / run / promote` present | yes |

## Built artifacts (rebuilt today)
- `dist/PetrolPumpERP.exe` (Qt application)
- `desktop/release/Petrol Pump ERP Setup 0.1.0.exe` (Electron installer; contains the new Python service and web build)

## Found and fixed while verifying
1. **The installer was carrying an old Python service.** `electron-builder` packs `desktop/sidecar-dist/pperp-api`, which was last built on 11 Oct. The installed app died on start with an Alembic revision error. Rebuilt with `pyinstaller api/pperp_api.spec --distpath desktop/sidecar-dist --workpath desktop/sidecar-build`, then `npm run dist`. **Always rebuild the sidecar before the installer** (this is in `desktop/README.md` step 2).
2. Two packaged tests were stale, not the product: the bridge list now includes `mode` and `shell` (added deliberately with the Network setup window; `shell.spec.ts` already expected it), and the manager now lands on Today, so the test goes to `#/tanks` after signing in. Test files only.

## NEEDS HUMAN REVIEW
- **Not tried on real hardware:** separate PCs, a real router/Wi-Fi, a real printer, a real mail server, BitLocker, the Windows scheduled task, and the firewall script (`install-main-pc.ps1` and `firewall-main-pc.ps1` were tested only with `-DryRun`). Work through `docs/LAN_MANUAL_CHECKLIST.md` before relying on it.
- Owner decisions still to confirm: V-06 default (one owner approves and locks; nobody is stopped from verifying their own entry); T-15 default of 5 litres testing; shortage cannot be pinned on a person because nobody is named per nozzle.
- Conflict messages show through each form's existing error text; there is no special "reload" button on every form.
- A concise "Shift close entry" screen without per-attendant assignments is still the main missing piece from the earlier build.
- Prettier `format:check` reports style differences in 24 desktop and 26 web files (line endings and formatting that predate this work). Not changed, to avoid a huge unrelated diff.
- Installer has the default Electron icon and is not code-signed.
- The Python suite takes about 48 minutes for `tests/api` + `tests/site`.

## Rules kept
No existing migration edited (new ones only); no existing permission meaning, AuditLog or backup logic changed (the audit lock wraps `AuditLogRepository.record` at runtime on a Main PC only); money stays Decimal; the only code that connects out is `mail_service.py`; nothing pushed.
