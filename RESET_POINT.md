# Reset Point - before the JS / Electron front-end migration

| Item | Value |
|---|---|
| Date | 2026-10-09 |
| Original branch | `feature/login-screen-enhancements` |
| Original HEAD | `652c589c5c7f231042ab2010de4409b7de3fb1d4` |
| Annotated tag | `reset/pre-js-frontend-2026-10-09` (points at the commit above) |
| Baseline tests | **996 passed, 0 failed** (`python -m pytest -q`, 5m20s). The brief expected 993 / ~23 min; the suite has since grown and ran faster. |
| Working tree at start | clean |
| Migration branch | `feature/js-frontend` (created from the commit above) |

## Safety copies (all outside the repo)

| What | Where | Result |
|---|---|---|
| Whole-repo git bundle (`git bundle create ... --all`, 12 refs) | `C:\Users\Asus\Projects\PetrolPumpERP-pre-js-2026-10-09.bundle` (12,770,880 bytes) | `git bundle verify`: **okay**, complete history, sha1 |
| Dev SQLite DB (+ `-shm`, `-wal`) copied from `app\` | `C:\Users\Asus\Projects\PetrolPumpERP-reset-2026-10-09\petrol_pump.db*` | copied |
| Built Qt exe | `C:\Users\Asus\Projects\PetrolPumpERP-reset-2026-10-09\PetrolPumpERP.exe` (116,634,823 bytes) | copied |

Deliberately NOT copied or touched: `%LOCALAPPDATA%\PetrolPumpERP\petrol_pump.db`
(the database of the *installed* app on this PC; it may hold real data).

## ROLLBACK

- **Return to the untouched original:** `git switch feature/login-screen-enhancements`
  (nothing in this migration is ever committed to that branch).
- **Exact commit:** the tag `reset/pre-js-frontend-2026-10-09` marks it:
  `git switch --detach reset/pre-js-frontend-2026-10-09`.
- **Repo folder lost or corrupted:**
  `git clone "C:\Users\Asus\Projects\PetrolPumpERP-pre-js-2026-10-09.bundle" PetrolPumpERP-restored`
  then `git switch feature/login-screen-enhancements`.
- **Throw the migration away entirely:** `git switch feature/login-screen-enhancements`
  then `git branch -D feature/js-frontend`.
- **Dev database:** copy the three `petrol_pump.db*` files back into `app\`.

## Commands for the owner (nothing here was pushed)

Push the tag (and, when ready, the branch):

```powershell
git push origin reset/pre-js-frontend-2026-10-09
git push origin feature/js-frontend
```

Copy the bundle and the reset folder to safe storage (adjust the drive letter):

```powershell
Copy-Item "C:\Users\Asus\Projects\PetrolPumpERP-pre-js-2026-10-09.bundle" "E:\Backups\" 
Copy-Item -Recurse "C:\Users\Asus\Projects\PetrolPumpERP-reset-2026-10-09" "E:\Backups\"
```

---

# Reset Point - before the 12-hour site-visit build (2026-10-12)

| Item | Value |
|---|---|
| Annotated tag | `reset/pre-12h-2026-10-12` |
| Commit | `923fd87dc8813705a2522d33182bc156c41db482` on `feature/js-frontend` |
| Bundle | `C:\Users\Asus\Projects\PetrolPumpERP-pre-12h-2026-10-12.bundle` (`git bundle verify`: okay) |
| Baseline tests | Python 1523 passed; web 317; desktop 33; Playwright 46 passed, 8 opt-in skipped |
| Work branch | `feature/site-visit-build` (never pushed) |

Rollback: `git switch feature/js-frontend`, or `git switch --detach reset/pre-12h-2026-10-12`.

---

# Reset Point - before the LAN multi-user build (2026-10-13)

| Item | Value |
|---|---|
| Annotated tag | `reset/pre-lan-2026-10-13` |
| Commit | `d17a399` on `feature/site-visit-build` |
| Bundle | `C:\Users\Asus\Projects\PetrolPumpERP-pre-lan-2026-10-13.bundle` |
| Baseline tests | Python 1804 passed, 1 skipped; web 360; desktop 33; Playwright 53 passed, 9 opt-in skipped |
| Work branch | `feature/lan-multi-user` (never pushed) |

Rollback: `git switch feature/site-visit-build`, or `git switch --detach reset/pre-lan-2026-10-13`.
