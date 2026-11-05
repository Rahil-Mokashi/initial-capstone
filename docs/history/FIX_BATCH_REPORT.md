# Fix batch report

Branch `feature/js-frontend`, new commits only (no rewrite, amend or squash), nothing pushed.
Full detail and every judgment call: `docs/migration/JS_MIGRATION_LOG.md` ("FIX BATCH" section).

## Step 0 - reset point (read-only): OK
Tag `reset/pre-js-frontend-2026-10-09` resolves to `652c589` (matches `docs/migration/RESET_POINT.md`); the original branch
`feature/login-screen-enhancements` is still `652c589`; `git bundle verify` says okay; the working tree was clean.
The earlier local rewrite touched only the new branch's own commits, not the tag or the original branch.

## Results per fix
| # | Fix | Result |
|---|---|---|
| 1 | Install-path length | **Done and verified.** Longest relative path 152 -> **107** characters (the longest migration .py: about 127 -> about 105). Shorter bundle layout, short default install folder (33 chars here), build fails above a budget of 130, startup preflight shows a clear message. Verified: deep install shows the message and starts no service; default install runs. |
| 2 | Electron fuses | **Done and verified on the installed build.** RunAsNode, NodeOptions and inspector off; asar integrity and only-load-from-asar on. `ELECTRON_RUN_AS_NODE=1` no longer turns the app into Node (an unfused control does). A tampered `app.asar` is refused. Offline checks all still pass. |
| 3 | Input scale | **Done.** Number boxes refuse a 4th decimal place (and letters, extra points, too many digits; minus only for adjustments), undo the edit as a whole, and explain why. Nothing is rounded. Server rule unchanged. |
| 4 | Variance bar | **Done.** Rebuilt from the Qt rules (two bars sized against the larger, one colour by classification, tag, variance line). Numbers printed, classification named with an icon, accessible labels, light and dark. Screenshots in `docs/`. |
| 5 | Printing harness | **Built, NOT verified on hardware.** `npm run print-test` plus `docs/PRINTING_TEST.md` with checklists. Only the safe modes were run here. |
| 6 | Dependency and build checks | **Done.** Lock differs from the reset tag by 9 added packages (FastAPI tree) and nothing else; Qt build still builds and starts. |
| 7 | Repeatable checks and docs | **Done**, with one honest exception for printing (below). `docs/OFFLINE_ACCEPTANCE.md` written but **not performed**. |

## Before / after numbers
| Measure | Before | After |
|---|---|---|
| Longest relative path in the app (all files) | 152 | **107** |
| Longest migration file path (loaded at run time) | about 127 | about 105 |
| Default install folder length | (user chose) | 33 (`%LOCALAPPDATA%\PPERP`) |
| Install folder allowed before the preflight blocks | about 80 spare | up to **132** characters |
| Build budget | none | fails above 130 |

Why 130: install folder plus longest inner path must stay under 240 (260 minus 20 spare), so 130 allows a 110-character folder.
Longest file is now a third-party `lxml` file, not ours.

## Final test counts (last full run, final code)
| Suite | Result |
|---|---|
| Python (996 existing + 107 API) | **1103 passed**, 0 failed (13m25s, no hang) |
| Web Vitest | **153 passed** (was 104) |
| Desktop Vitest | **33 passed** (was 29) |
| Playwright, default suite | **29 passed**, 8 opt-in skipped |
| Opt-in via npm: `test:packaged --install` | 4 passed |
| Opt-in: `test:deep-path` | 1 passed (after fixing the test, see below) |
| Opt-in: `test:screenshots` | 2 passed |
| Opt-in: `test:print-spike` | skips itself as INCONCLUSIVE |
| Web lint/typecheck/format, desktop lint/typecheck/format | clean |
| Build offline gate | passed |
| Qt PyInstaller build from this branch | built (4m50s, 116.6 MB) and started on a fresh database |

## Failures found while doing this (reported, not hidden)
- `test:deep-path` first **failed** (timeout). The product was right: its "path too long" window appeared (that is the error you saw pop up). The test was wrong: it still used Playwright's Electron mode, which the new fuses disable. I rewrote the test to attach differently; its expectations about the message were not loosened.
- `test:print-spike` returned success against "Microsoft Print to PDF" but printed nothing, the same meaningless result as before. I changed it so it no longer counts as a pass: it skips with "INCONCLUSIVE" when only virtual printers exist.
- The first lock bumped `typing_extensions` 4.15.0 to 4.16.0 as a side effect of an `anyio` version. It is now back at 4.15.0 by pinning `anyio` 4.14.0 (reasoning in the log).
- My first deep-path/installed tests left an app running after a failure and polluted the next test; tests now always stop what they start.

## Still unverified
- **Printing on real hardware** (paper, margins, cut, drawer, thermal width): not done. Steps in `docs/PRINTING_TEST.md`.
- **The offline acceptance run** (install, all networks physically off, log in, view tanks, record a reading, log out): not done, I cannot do it from here. Steps in `docs/OFFLINE_ACCEPTANCE.md`.
- Installer is unsigned (Windows SmartScreen may warn) and uses the default Electron icon.
- Running the classic app and the new app at the same time on the same live database: untested.

## NEEDS HUMAN REVIEW
- Nothing was changed in `app/`, Alembic (including file names), RBAC meaning, AuditLog, backup logic, the Qt entry point or the Inno Setup installer.
- `GrantFileProtocolExtraPrivileges` (an Electron fuse) is still on by default. It was not in the list and turning it off might affect the error screen; worth a look.
- The sidecar bundle still contains packages it does not need (`lxml`, `mypy`, `psutil`, `setuptools`, `yaml`) because they are installed globally on this machine. Excluding them would shrink it; not done.
- Policy decisions from the first report still stand for you to confirm (server-side forced password change, rejecting over-precise decimals, fuel lookup permission).
- Installed apps share the Qt app's database folder by default (`%LOCALAPPDATA%\PetrolPumpERP`).

## Where things are
`docs/history/FIX_BATCH_REPORT.md` (this), `docs/migration/JS_MIGRATION_LOG.md`, `docs/PRINTING_TEST.md`, `docs/OFFLINE_ACCEPTANCE.md`, `desktop/README.md`
(all scripts), screenshots `docs/js-variance-*.png`.
