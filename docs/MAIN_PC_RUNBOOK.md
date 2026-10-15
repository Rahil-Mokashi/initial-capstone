# Main PC runbook

Written for: whoever looks after the pump's Main PC (the owner's representative or a technician). Plain steps, in the order you need them.

The **Main PC** holds the one database and runs all day. Every other PC at the pump is a **Client PC**: a window onto the Main PC's data. Nothing connects in from the internet. The only thing that ever connects out is the optional daily summary email (off unless an owner turns it on).

## 1. Setting up the Main PC (once)

1. Pick a PC that stays on, with a fixed network address (give it a reserved address in the router, for example 192.168.1.10).
2. **Turn on BitLocker** for the drive that will hold the data (Windows: Manage BitLocker). This protects the data if the PC or its disk is stolen. System health shows a red "Disk encryption" line until it is on. Keep the recovery key somewhere safe (not on this PC).
3. Set the network to **Private** (Settings > Network). Use a strong Windows password for every administrator account on this PC.
4. Open PowerShell **as Administrator** and run, with your own address and network:
   `.\scripts\lan\install-main-pc.ps1 -Exe 'C:\PetrolPumpERP\pperp_api.exe' -Address 192.168.1.10 -Subnets 192.168.1.0/24 -DryRun`
   Read what it says it will do, then run it again without `-DryRun`. It protects the data folder, creates the private authority and keys, opens the firewall for those two ports and that network only, and registers a task that starts the program at every boot (no window, no sign-in needed).
5. Give the Main PC's own window a device identity: `pperp_api.exe lan enrol-local --name "Main PC window" --out device.json`, open the app, **Network setup > Import a device file**, then **delete device.json**.
6. Sign in as an owner, open **Devices > Add a device**. On each other PC open **Network setup > Client PC**, type the address, the pairing code and a name for that PC. **Compare the fingerprint** on the two screens before pressing "They match".

## 2. Every day

Nothing. The Main PC takes backups by itself and runs its safety checks every night. Once a week an owner or the technician opens **System health**: everything should say **Good**.

| It says | What to do |
|---|---|
| Latest backup: Look or Problem | The Main PC may have been off. Press **Run the checks now**. If it stays red, see section 4 |
| Database integrity or Audit log: Problem | **Stop entering data.** Do not restore anything yet. Copy the whole data folder to a safe place and call whoever maintains the software |
| Copy off this PC: Look | Set a USB or network folder for off-device backups (Company Profile) and a backup passphrase (System health) |
| Disk encryption: Problem or Look | Turn BitLocker on (section 1, step 2) |
| Free space: Problem | Free some disk space on the Main PC; old backups live in `backups\` next to the database |
| A PC shows nothing seen for days | Is it switched on and on the pump's network? Press Test connection in its Network setup |

## 3. Backups

* Automatic: a backup is taken when the newest one is older than the Owner Choice "Take a backup every (hours)" (24). Each backup is verified when made.
* Nightly: the database file is checked, the audit log is verified, and the newest backup is copied to the off-device folder **encrypted** with the backup passphrase.
* The **backup passphrase** is set on System health. **Write it down and keep it away from the Main PC.** Without it the off-device copies cannot be opened by anyone, including the people who built the software.
* Where things are: the database and its `backups\` folder are under the data folder you chose in the install script (default `C:\ProgramData\PetrolPumpERP\data`). Only Windows administrators can open it.

## 4. If the Main PC dies: restore and promote (tested)

You need: the newest backup (from the off-device folder, ending `.db.enc`, or from the old `backups\` folder if the disk survived), the backup passphrase for a `.enc` file, and a replacement PC.

1. Prepare the replacement as in section 1, steps 1 to 3 (address, BitLocker, Private network). Install the application.
2. In Administrator PowerShell, restore the backup: `pperp_api.exe lan promote --backup "E:\PumpBackups\petrol_pump_....db.enc"` (it asks for the passphrase). It refuses a damaged file, restores, brings the database up to the current version, **verifies the audit chain**, and prints how many users, shifts and audit entries came back. If it prints "PROBLEMS", stop and call for help: the backup was altered or damaged.
3. Run `install-main-pc.ps1` (section 1, step 4). This creates a **new** private authority: the old keys belonged to the dead PC and are not carried over, on purpose.
4. **Add every PC again** from Devices (pairing code each). Devices listed from the old database are shown as enrolled but their certificates no longer work; remove them from the list afterwards.
5. Open Daily Report for a recent day and compare a figure with the paper. Then carry on.

Expect about an hour for a technician. Anything entered after the last backup is lost: check which day the backup is from and re-enter from the paper bundle.

## 5. Replacing or losing a Client PC

Devices > **Remove** the lost or stolen PC (it stops working at once, even if someone has its certificate). Set up its replacement with a new pairing code. A removed PC leaves no data behind: Client PCs keep no copy.

## 6. Changing the Main PC's address

Re-run the install script with the new address (it makes a new server certificate). Every Client PC must then open **Network setup** and be paired again.

## 7. Never

* Never open the database file with another program while the Main PC is running, and never copy it by hand while it runs (use the backups).
* Never run the application in Single PC mode on the Main PC: it refuses, because two programs writing to one database would damage the audit log.
* Never share the pairing code, the backup passphrase or the mail password in a message.
* Never open the Main PC to the internet (no port forwarding). It is built for the pump's own network only.

## 8. What is and is not protected

Protected: the database is only reachable through the Main PC's program, over an encrypted, mutually authenticated connection, from enrolled PCs on the pump's network, and only by people who sign in; folders are limited to Windows administrators; keys are under Windows data protection; off-device copies are encrypted; every change is audit-logged and the log is checked every night.

**Not** protected by the software, and why you must still care: anyone who can sign in to the Main PC as a Windows administrator can read the database, and so can anyone who steals the disk if BitLocker is off. Physical security of the Main PC, strong administrator passwords and BitLocker are part of the system.
