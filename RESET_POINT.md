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
