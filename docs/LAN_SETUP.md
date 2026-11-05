# Setting up several PCs at the pump

Written for: the person installing the system (owner or technician). It is the short version; `docs/MAIN_PC_RUNBOOK.md` has the care and recovery steps and `docs/adr-lan-multi-user.md` the reasons.

## The idea in three lines

One PC is the **Main PC**: it holds the database and runs all day. Every other PC is a **Client PC**: it shows the Main PC's data live and keeps no copy. Nothing connects in from the internet.

## What you need

* A PC that stays on, with a fixed address on the pump's network (reserve it in the router), for the Main PC.
* The other PCs on the same network (cable or Wi-Fi), each with the application installed.
* An owner's sign-in, to add devices.

## 1. The Main PC (once)

1. Set the network to **Private**. Turn on **BitLocker** for the drive holding the data.
2. As Administrator in PowerShell: `.\scripts\lan\install-main-pc.ps1 -Exe '<path to pperp_api.exe>' -Address <this PC's address> -Subnets <your network, e.g. 192.168.1.0/24> -DryRun`. Read the list, then run it without `-DryRun`.
3. `pperp_api.exe lan enrol-local --name "Main PC window" --out device.json`, then in the app: **Network setup > Import a device file**. Delete `device.json`.
4. If this PC already had data from Single PC use: take a backup first, then `pperp_api.exe lan promote --backup <that backup>` into the Main PC's data folder (see the runbook, section 4), before step 2's first start.

## 2. Each Client PC

1. On the Main PC: sign in as an owner, **Devices > Add a device**. A code (10 characters) and a **fingerprint** appear. The code works once and lasts 10 minutes.
2. On the Client PC: open the app, on the sign-in page press **Network setup**, choose **Client PC**, type the Main PC's address, the name for this PC and the code, press **Check the Main PC**.
3. **Compare the fingerprint** shown on the Client PC with the one on the Main PC's screen, character by character (spoken or photographed). Only if they are the same press **They match - pair this PC**.
4. Press **Test connection**. The sign-in page now says the data is on the Main PC; sign in as usual.

## 3. Day to day

* The top bar shows a light: green = connected live, amber = connected but refreshing every 20 seconds, red = the Main PC cannot be reached (you can read what is on screen; nothing can be saved until it is back).
* Two people editing the same record: the second to save is told who changed it and when, and reloads. Nobody's work is overwritten silently.
* Each shift: the cashier closes it on **Close Shift** (entered), the accountant **verifies** it on **Review**, an owner **approves** and **locks** it. A locked shift cannot change; an owner can **reopen** it with a reason.
* Owners see the **Daily Digest** as their home and can mark a day reviewed.

## 4. When something goes wrong

| What you see | What it means / do this |
|---|---|
| "Cannot reach the Main PC" page | Main PC off, or this PC is off the network. Check both; it retries by itself |
| "This PC is not allowed on the Main PC" | This PC was removed, or its network is not in the allowed list. An owner adds it again from Devices |
| Pairing says "failed" | Wrong or used code, or older than 10 minutes. Ask for a new one |
| Fingerprints differ | **Stop.** Something is between the two PCs. Tell the owner; do not press "They match" |
| System health shows red | See the runbook, section 2 |

## What is not covered here

Real-hardware behaviour (printers on a Client PC, Wi-Fi roaming, power cuts) was not tested by the build; use `docs/LAN_MANUAL_CHECKLIST.md` on site. The setup scripts were tested only in dry-run mode.
