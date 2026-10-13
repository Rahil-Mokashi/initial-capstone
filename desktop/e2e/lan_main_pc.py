"""TEST FIXTURE ONLY: a real Main PC (mutual TLS, device tokens, enrolment listener) on 127.0.0.1 for the Electron tests.

    PETROL_PUMP_DB_PATH=<copy of the template db> python desktop/e2e/lan_main_pc.py --dir <folder for keys>

It uses InsecureTestProtector (keys are NOT DPAPI-protected) and skips the Windows folder protection, so it can never be mistaken
for a Main PC: the real one is api.lan.server.run_main. Prints one JSON line when ready, then reads commands from stdin:
    pair <username>        -> {"code": "...", "fingerprint": "..."}   (starts the enrolment listener)
    local <name> <file>    -> console-enrols a device and writes its bundle file
    revoke <device-id>     -> removes the device
    quit
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if not os.environ.get("PETROL_PUMP_DB_PATH"):
    sys.exit("PETROL_PUMP_DB_PATH must be set - refusing to use the default database.")

import uvicorn  # noqa: E402

from api.lan import server, writelock  # noqa: E402
from api.lan.config import LanConfig  # noqa: E402
from api.lan.pki import InsecureTestProtector, Pki  # noqa: E402
from app.database import connection  # noqa: E402
from app.models.user import User  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--requests-per-minute", type=int, default=600)
    args = ap.parse_args()

    config = LanConfig(mode="main", bind_address="127.0.0.1", port=free_port(), pairing_port=free_port(),
                       allowed_subnets=["127.0.0.0/16"], requests_per_minute=args.requests_per_minute)
    pki = Pki(Path(args.dir) / "pki", InsecureTestProtector())
    pki.ensure(config)
    writelock.install(connection.engine)
    lan = server.build_lan(config, pki, connection.SessionLocal)
    web_dir = os.environ.get("PPERP_WEB_DIR")
    app = server.build_main_asgi(config, lan, connection.SessionLocal, Path(web_dir) if web_dir else None, on_block=lan.record_block)
    uv = uvicorn.Server(server.main_uvicorn_config(app, config, pki))
    threading.Thread(target=uv.run, daemon=True).start()
    while not uv.started:
        time.sleep(0.05)
    print(json.dumps({"ready": True, "host": "127.0.0.1", "port": config.port, "pairing_port": config.pairing_port,
                      "fingerprint": pki.ca_fingerprint()}), flush=True)

    def user_id(username: str) -> str:
        with connection.SessionLocal() as db:
            return db.query(User).filter_by(username=username).one().id

    for line in sys.stdin:
        cmd = line.split()
        if not cmd:
            continue
        if cmd[0] == "quit":
            break
        if cmd[0] == "pair":
            code, minutes = lan.start_pairing(user_id(cmd[1]))
            print(json.dumps({"code": code, "minutes": minutes, "fingerprint": pki.ca_fingerprint()}), flush=True)
        elif cmd[0] == "local":
            result = lan.devices.enrol_local(cmd[1].replace("_", " "), user_id("owner1"))
            bundle = {"host": "127.0.0.1", "port": config.port, "ca_pem": pki.ca_pem().decode(), "cert_pem": result.cert_pem,
                      "key_pem": result.key_pem, "token": result.token, "device_name": result.name}
            Path(cmd[2]).write_text(json.dumps(bundle), encoding="utf-8")
            print(json.dumps({"device_id": result.device_id, "file": cmd[2]}), flush=True)
        elif cmd[0] == "revoke":
            lan.devices.revoke(cmd[1], user_id("owner1"), "removed by the test")
            print(json.dumps({"revoked": cmd[1]}), flush=True)
    lan.listener.stop()
    uv.should_exit = True
    time.sleep(0.5)
    with connection.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")


if __name__ == "__main__":
    main()
