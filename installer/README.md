# Building the installer

`petrol_pump_erp.iss` is an [Inno Setup](https://jrsoftware.org/isinfo.php) script that wraps the standalone `dist/PetrolPumpERP.exe` (built by `pyinstaller petrol_pump_erp.spec`) into a proper Windows installer: Start Menu shortcuts (including the three `docs/*.md` guides), an optional desktop shortcut, and a registered uninstaller.

## Building locally

Requires Inno Setup 6 (`winget install JRSoftware.InnoSetup` or `choco install innosetup`).

```
pyinstaller petrol_pump_erp.spec
iscc installer\petrol_pump_erp.iss
```

Output: `installer/output/PetrolPumpERP-Setup-<version>.exe` (not checked into git - same as `dist/`).

## Building via CI

`.github/workflows/release.yml` does this automatically whenever a version tag is pushed (`git tag v1.0.0 && git push origin v1.0.0`), and attaches both the standalone exe and the installer to a GitHub Release.

## Notes

- The installer only places the application files under `{app}` (Program Files by default). It never touches `%LOCALAPPDATA%\PetrolPumpERP` (the database, backups, logs, reports) - uninstalling never deletes historical data, matching CLAUDE.md's "never remove historical financial data".
- `PrivilegesRequired=lowest` in the script - the app doesn't need admin rights to install or run, since all of its writable state lives under the current user's own `%LOCALAPPDATA%`.
- Bump `#define MyAppVersion` in `petrol_pump_erp.iss` before cutting a release; it drives both the installer's displayed version and its output filename.
