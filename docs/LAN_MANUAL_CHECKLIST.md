# Manual checklist: several PCs at the pump

Do these on real PCs before relying on the system. Tick each one; write the date and who did it. The automated tests used one computer talking to itself over real encrypted connections; **none of this has been tried on separate PCs, a real router, a real printer or a real mail account.**

## A. Main PC

- [ ] BitLocker is on for the data drive; recovery key stored away from the PC.
- [ ] The network profile is Private. The PC does not sleep (power settings: never sleep when plugged in).
- [ ] `install-main-pc.ps1 -DryRun` output was read, then the real run finished without errors.
- [ ] After a reboot, with nobody signed in, the other PCs can still connect (the task starts at boot).
- [ ] Kill `pperp_api.exe` in Task Manager: it comes back within about a minute.
- [ ] In Windows Firewall the rule "Petrol Pump ERP - Main PC" exists, Private profile only, allowed remote addresses = the pump's network only.
- [ ] From a PC **outside** the allowed network (phone hotspot, another subnet) the Main PC cannot be reached.
- [ ] The data folder cannot be opened by a standard (non-administrator) Windows user.

## B. Client PCs (do for at least two, one of them on Wi-Fi)

- [ ] Pairing: the fingerprints match on both screens; pairing works once; the same code a second time fails.
- [ ] A wrong code five times kills the code.
- [ ] Sign in, open Tanks, make a change on one PC; the other PC shows it within a few seconds without reloading.
- [ ] Two PCs edit the same employee: the second save says "Changed by <name> at <time>".
- [ ] Unplug the Client's network cable: red light and "cannot be reached"; saving is refused; plug back in: it recovers by itself.
- [ ] Switch the Main PC off while a Client is open: the Client shows the "Cannot reach the Main PC" page, then recovers when the Main PC is back.
- [ ] Devices > Remove a PC: it is refused at its next request (within seconds), and cannot be paired again with the old identity.
- [ ] A Client PC prints a daily report to the real printer (print preview, print, PDF, Excel).

## C. The review chain

- [ ] Cashier closes a shift on one PC; the accountant on another PC sees it as Entered, presses Verify; an owner approves and locks; the accountant's screen updates on its own.
- [ ] Try to change a figure on a locked shift (a sale, a card total, cash): it is refused. An owner reopens with a reason; the chain starts again.
- [ ] Change a figure after Verified: the shift goes back to Entered by itself.

## D. Safety

- [ ] System health: every line Good (or you understand each Look).
- [ ] A backup appears in `backups\`; with a passphrase and an off-device folder set, an encrypted copy (`.db.enc`) appears there; open it with `lan promote` on a test PC.
- [ ] Restore-and-promote rehearsal on a spare PC with a real backup: the numbers match the old Main PC, the audit chain is reported unbroken, every PC can be paired again.
- [ ] Unplug the power of the Main PC while a PC is saving a sale: after power returns, the program starts, the database passes the integrity check, and no half-saved sale exists.

## E. Optional email (only if used)

- [ ] Send a test message to your own address; it arrives. The text has no names.
- [ ] Wrong password: the screen says so in words and nothing else slows down.
- [ ] The summary arrives once a day, after the chosen hour, with figures only.

## F. Offline

- [ ] With the internet cable unplugged everything above still works.
- [ ] No traffic leaves the pump's network except the optional mail (check the router's log if you can).
