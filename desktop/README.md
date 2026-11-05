# desktop - Electron shell for the new UI

Electron main/preload (TypeScript), the Playwright end-to-end tests, and packaging. The web UI lives in `../web`,
the local API in `../api`. Decision record: `../docs/adr-js-frontend.md`. Running log: `../docs/migration/JS_MIGRATION_LOG.md`.

**Terminal note:** some terminals set `ELECTRON_RUN_AS_NODE=1`, which makes Electron behave as plain Node. Every
script here removes it; if you run `electron` by hand, clear it first
(`Remove-Item Env:ELECTRON_RUN_AS_NODE`).

## Everyday commands (run in this folder)

| Command         | What it does                                                                        |
| --------------- | ----------------------------------------------------------------------------------- |
| `npm install`   | install dependencies (downloads Electron once)                                      |
| `npm run build` | bundle main and preload into `dist/` (build `../web` first)                         |
| `npm start`     | build and open the app against your dev database                                    |
| `npm test`      | unit tests (request policy, sidecar lifecycle, install-path preflight)              |
| `npm run e2e`   | Playwright against the real Electron app and real Python API (seeds a throwaway DB) |
| `npm run dist`  | build the installer: `release/Petrol Pump ERP Setup 2.0.2.exe` (see below)          |

## Building the installer

1. `cd ../web && npm run build` (the UI, with the offline check)
2. `cd .. && pyinstaller api/pperp_api.spec --noconfirm --distpath desktop/sidecar-dist --workpath desktop/sidecar-build` (the Python API)
3. `cd desktop && npm run dist`

The build runs `scripts/after-pack.cjs`, which (a) applies the Electron fuses and (b) measures the longest file path
inside the app and **fails the build above 130 characters** (see the log, Fix 1). Code signing is not done yet.

## Opt-in test suites (skipped by `npm run e2e`)

| Command                              | What it checks                                                                                                                                                | Notes                                                                                                                                                            |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `npm run test:packaged -- --install` | the INSTALLED app: starts, Tanks works, `ELECTRON_RUN_AS_NODE=1` does not turn it into Node, the inspector and `NODE_OPTIONS` are refused, offline rules hold | `--install` silently installs `release/...Setup.exe` into the default folder first. Without it, the app must already be installed (or set `PPERP_PACKAGED_EXE`). |
| `npm run test:deep-path`             | installs into a deliberately deep folder, checks the "path too long" message, uninstalls                                                                      | Shows the error window briefly. It leaves the default install unregistered, so run `test:packaged -- --install` again afterwards.                                |
| `npm run test:screenshots`           | regenerates the screenshots in `../docs`                                                                                                                      |                                                                                                                                                                  |
| `npm run test:print-spike`           | tries a silent print to the Windows default printer                                                                                                           | Skips itself ("INCONCLUSIVE") when only virtual printers (PDF, OneNote) exist; use `../docs/PRINTING_TEST.md` on a real printer.                                      |

The installed build has its Node inspector switched off (fuse), so these tests attach over Chromium's remote
debugging port instead of Playwright's Electron mode.

## Printing on a real printer

`npm run print-test -- --list` / `--printer "<name>"` / `--to-pdf <folder>`: see `../docs/PRINTING_TEST.md`.

## Measuring

`scripts/measure.ps1` times start-up and idle memory for the new app against the Qt exe (see the report).
