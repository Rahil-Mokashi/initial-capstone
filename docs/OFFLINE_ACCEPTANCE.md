# Offline acceptance test (to be done by the owner)

**Status: NOT performed.** I could not do this step myself: it needs a real PC with its network physically
switched off, and I have no way to disconnect this machine or to watch it from outside. What I did run are
automated checks (the app makes no request outside 127.0.0.1, the page cannot reach the internet, the build
contains no external URLs). Those are good evidence, but the final proof is this manual run on a clean PC.

The point: the new app must work with **no internet at all**, from install to log-out.

## Before you start
- A Windows PC that has never run the new app (a clean one is best), with the installer
  `Petrol Pump ERP Setup 2.0.0.exe` copied onto it (USB stick is fine; this is built by `npm run dist` in the `desktop` folder).
- A test database is NOT needed: the app creates its own on first start. Do not use real business data for this test.
- A sign-in. On a brand-new database the only user is `admin` with password `Admin@123`, and the app will force
  you to choose a new password at the first sign-in (that is expected and part of the test).

## Steps
1. **Disconnect everything.** Turn Wi-Fi off (Settings, Network & internet, Wi-Fi: Off). Unplug the Ethernet cable.
   Turn off any mobile hotspot or tethering. Open a browser and try any website; it must fail.
   (Optional, stronger: turn on Airplane mode.)
2. **Install.** Double-click the installer. Accept the default folder (it is short on purpose: `C:\Users\<you>\AppData\Local\PPERP`).
   - [ ] Installer finished without asking for the internet
3. **Start the app** from the Start menu or desktop shortcut.
   - [ ] A window titled "Petrol Pump ERP" opens and shows the Sign in screen within about 10 seconds
   - [ ] No error window ("The application could not start")
4. **Log in.** Username `admin`, password `Admin@123`. The app asks for a new password; choose one
   (8+ characters, upper and lower case, a number and a symbol) and write it down.
   - [ ] Sign-in works; password change works
5. **View tanks.** Click **Tanks** in the left menu.
   - [ ] The Tanks screen opens (it will say "No tanks yet" on a new database)
   - [ ] To get something to look at: **Add tank** (code `T1`, choose a fuel type, capacity `10000`, opening stock `2500`). The tank card appears.
6. **Record a reading.** On the T1 card choose **Record reading**.
   - It needs an employee to choose from. On a brand-new database there is none, so add one in the classic app
     (Employees) or skip to **Receipt** instead: on the T1 card choose **Receipt**, quantity `100`, **Record receipt**.
   - [ ] A green confirmation appears and the stock changes (2,600.000)
   - If you did have an employee: **Record reading**, pick the employee, physical stock `2590`, **Save reading**.
     - [ ] Confirmation appears; open the tank, the Readings tab shows the new line
7. **Log out.** Click **Log out** at the top right.
   - [ ] You are back on the Sign in screen
8. **Close and restart.** Close the window, start the app again, sign in with the new password.
   - [ ] Your tank and its stock are still there
9. **Check the network stayed off the whole time.** Leave Wi-Fi/Ethernet off until step 8 is done.

## What to report
For each box: Yes / No, plus anything odd you saw (a spinner that never ends, an error message, a window that
flashed). Please also note: the PC model, Windows version, and whether any antivirus popup appeared (the
installer is not code-signed yet, so Windows SmartScreen may warn: "More info" then "Run anyway").

## If something fails
- The app writes a log next to its database: `%LOCALAPPDATA%\PetrolPumpERP\petrol_pump_erp.log`. Send it.
- If the error window appears, take a photo or copy its text; it states what is wrong.
- A message saying the app is "installed in a folder whose path is too long" means a very deep install folder was chosen; reinstall to `C:\PPERP`.

## What the automated checks already cover (for reference)
- `npm run test:packaged` (in `desktop`): installed app starts, outside requests are blocked, strict content policy, minimal bridge.
- `npm run e2e`: a whole session makes zero requests outside 127.0.0.1; the main-process blocker cancels outside requests even when the page policy is absent.
- `npm run build` (in `web`): fails if any external URL is in the built UI.
