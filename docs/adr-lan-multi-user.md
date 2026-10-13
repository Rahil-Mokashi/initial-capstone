# ADR: Several PCs on the pump's network, one Main PC (LAN multi-user)

Status: accepted by the owner's brief of 2026-10-13. Written for: the developer and whoever installs the pump's PCs.

## Decision

One PC at the pump is the **Main PC**. It runs the Python API and holds the **one** SQLite database. Every other PC is a **Client PC**:
an Electron window that reads and writes live, over the pump's local network, to the Main PC. Clients keep no copy of the data and queue
no writes. If the Main PC cannot be reached a Client shows a read-only "cannot reach the Main PC" screen; nothing is lost because
nothing was ever stored on the Client.

Nothing connects in from the internet. The only internet use that will ever exist is an **optional, off-by-default, outbound,
read-only owner summary email** (Phase 6).

## Three setup modes

| Mode | What runs | Default |
|---|---|---|
| **Single PC** | Exactly today's app: sidecar on `127.0.0.1`, random port, per-launch secret. | **Yes**, and nothing in this work changes it. |
| **Main PC** | The API bound to the owner-chosen LAN address and port, over mutual TLS, started by a scheduled task at boot (no window and no login needed). | No |
| **Client PC** | Electron only; talks to the Main PC through a loopback proxy inside Electron that holds the device certificate. | No |

The mode is read from a small JSON file (`lan.json`). No file means Single PC. A Main PC **refuses to start** if any protection
cannot be completed (no CA, no certificate, key files not protected, bad bind address, empty subnet list, database folder not
restricted). It never falls back to plain HTTP.

## How a Client is trusted

* The Main PC owns a private **certificate authority** (CA), created on first setup. It signs the server certificate (whose names
  are the Main PC's chosen address and host name) and one **client certificate per device**.
* The listener demands a valid client certificate (TLS 1.2 or newer). Without one the TLS handshake fails; no HTTP is exchanged.
* A Client **pins** the CA it received at enrolment; it will not talk to a server whose certificate does not chain to that CA.
* A device also carries a random **device token** (stored only as a hash on the Main PC). A stolen certificate without the token, or a
  stolen token without the certificate, gets nothing. Revoking a device marks the token revoked (effective on the next request)
  and adds the certificate to the revocation list.
* **Enrolment** is done by the owner: "Devices" screen, "Add a device", which shows a short single-use pairing code valid for 10
  minutes. Only while a code is active does a second, enrolment-only listener exist (a different port; closed otherwise). The code is
  never sent: the Client and the Main PC prove they know it with an HMAC over the CA fingerprint and a nonce, so a machine in the
  middle that substitutes its own CA is detected. Five wrong tries kill the code. The Client's private key is produced on the Main PC
  and sent once inside TLS; the Main PC keeps only the fingerprint.
* Keys are stored under Windows **DPAPI** (machine scope on the Main PC, via Electron `safeStorage` on a Client) in folders whose
  access list is limited to SYSTEM and Administrators.
* People still sign in with their own user name and password, with the existing lock-out, session expiry and (new) rate limit. Every
  event is audit-logged with user, **device name** and **IP address**.

## Live data

* SQLite in WAL mode with a busy timeout; one writer at a time. All writes are serialised by a process-wide write lock on the Main
  PC, which also keeps the **audit hash chain** correct (the chain reads the newest entry and then appends: two writers must never
  interleave). Reads run in parallel.
* The checks engine runs only on the Main PC, after writes, as today.
* **Optimistic locking**: editable records carry a version number; a save with a stale version is refused with "Changed by X at
  HH:MM", and the person reloads. Nobody's work is silently overwritten.
* The Main PC pushes small "something changed" messages (server-sent events); a Client falls back to polling every 15 to 30 seconds.
  Screens show "last updated" and a green/amber/red connection light.
* All times come from the **Main PC's clock**, never from a Client.

## Rejected alternatives

| Alternative | Why not |
|---|---|
| A database on every PC plus synchronisation | Two PCs can both change one figure; merging money is a research problem. A pump needs one truth. |
| The SQLite file on a shared folder | SQLite over SMB loses locks and corrupts under concurrent writers; nothing guards who may open it. |
| A cloud server | Forbidden by the offline rule (CLAUDE.md); the pump must run with the internet cable out. |
| PostgreSQL | A real option, but a second product to install, secure, back up and explain to a non-technical owner. See below. |

**What would justify PostgreSQL later:** sustained write contention (the Main PC regularly waits more than a second for the write
lock), more than roughly 30 simultaneous active clients, a second pump sharing the data, or a need to run reports while data entry
continues without slowing it. Until one of those is observed, one SQLite file behind one process is simpler and safer.

## What the Main PC runs as

A Windows service is preferred. The sidecar is a plain console program and the project has no service wrapper (pywin32 or NSSM would
be a new dependency), so the first version installs a **scheduled task** that starts at boot as SYSTEM, with "restart on failure". It
needs no window and no sign-in. Same effect for the owner; replace with a real service later if wanted.

## Limits kept on purpose

The Client's windowing layer (Electron fuses, request blocker, strict CSP) stays as it is. In Client mode the renderer still talks only
to `http://127.0.0.1:<port>` (the loopback proxy), so the existing offline checks keep passing. `/docs`, `/redoc` and `/openapi.json` are
off in every mode.
