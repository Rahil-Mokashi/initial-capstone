"""Console commands for the person installing the Main PC (run as an Administrator on that PC):

  pperp_api.exe lan init --address 192.168.1.10 --subnets 192.168.1.0/24 [--port 8443] [--pairing-port 8444] [--name pump-main]
  pperp_api.exe lan status
  pperp_api.exe lan enrol-local --name "Main PC window" --out bundle.json
  pperp_api.exe lan run            (what the start-at-boot task runs)
  pperp_api.exe lan promote --backup <file> [--db <path>]   (a replacement Main PC: restore the newest backup and check it)
"""

import argparse
import json
import sys
from pathlib import Path

from api.lan import config as cfg
from api.lan import fs_security
from api.lan.config import LanConfig, LanConfigError, lan_dir


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lan")
    sub = p.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("--address", required=True)
    init.add_argument("--subnets", required=True, help="comma separated, for example 192.168.1.0/24")
    init.add_argument("--port", type=int, default=8443)
    init.add_argument("--pairing-port", type=int, default=8444)
    init.add_argument("--name", action="append", default=[], help="extra host name for the certificate")
    sub.add_parser("status")
    local = sub.add_parser("enrol-local")
    local.add_argument("--name", required=True)
    local.add_argument("--out", required=True)
    sub.add_parser("run")
    promote = sub.add_parser("promote")
    promote.add_argument("--backup", required=True)
    promote.add_argument("--passphrase", default="", help="for an encrypted (.enc) copy; asked for if left out")
    promote.add_argument("--db", default=None, help="target database path (default: where the Main PC keeps its data)")
    return p


def run(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        return _dispatch(args)
    except LanConfigError as exc:
        print(f"Main PC setup: {exc}", file=sys.stderr)
        return 2


def _dispatch(args) -> int:
    from api.lan.pki import DpapiProtector, Pki

    if args.cmd == "promote":
        from api.lan.promote import PromoteError, promote
        from app.database import connection

        try:
            phrase = args.passphrase
            if args.backup.endswith('.enc') and not phrase:
                import getpass

                phrase = getpass.getpass('Backup passphrase: ')
            result = promote(args.backup, args.db or connection.DB_PATH, phrase)
        except PromoteError as exc:
            print(f"Promote stopped: {exc}", file=sys.stderr)
            return 2
        print(f"Restored {result.db_path}: {result.users} users, {result.shifts} shifts, {result.audit_entries} audit entries.")
        print("Audit chain: " + ("unbroken." if result.audit_chain_ok else f"PROBLEMS: {result.problems}"))
        print("Next: run `lan init` (a new private authority) and add every PC again from the Devices screen.")
        return 0 if result.audit_chain_ok else 3
    if args.cmd == "init":
        config = LanConfig(mode="main", bind_address=args.address, port=args.port, pairing_port=args.pairing_port,
                           allowed_subnets=[s.strip() for s in args.subnets.split(",") if s.strip()], server_names=args.name)
        config.validate_for_main()
        fs_security.harden(lan_dir())
        pki = Pki(lan_dir() / "pki", DpapiProtector())
        pki.ensure(config)
        cfg.save(config)
        print(f"Main PC configured on {config.bind_address}:{config.port}.")
        print(f"Authority fingerprint (shown again when a device is added): {pki.ca_fingerprint()}")
        return 0
    config = cfg.load()
    if config.mode != "main":
        print("This PC is not set up as the Main PC (no lan.json).")
        return 1
    if args.cmd == "status":
        pki = Pki(lan_dir() / "pki", DpapiProtector())
        print(json.dumps({"config": config.model_dump(), "keys_folder_protected": fs_security.is_hardened(lan_dir()),
                          "authority_fingerprint": pki.ca_fingerprint() if pki.has_ca() else None}, indent=2))
        return 0
    if args.cmd == "run":
        from api.lan.server import run_main

        return run_main()
    if args.cmd == "enrol-local":
        return _enrol_local(config, args.name, Path(args.out))
    return 1


def _enrol_local(config: LanConfig, name: str, out: Path) -> int:
    from api.lan.devices import DeviceService, PairingManager
    from api.lan.pki import DpapiProtector, Pki
    from app.database import connection
    from app.main import _initialize_database
    from app.models.user import User
    from app.models.role import Role

    _initialize_database()
    pki = Pki(lan_dir() / "pki", DpapiProtector())
    with connection.SessionLocal() as db:
        owner = db.query(User).join(Role).filter(Role.name.in_(["OWNER", "ADMIN"])).order_by(User.created_at).first()
        if owner is None:
            raise LanConfigError("There is no owner or administrator account yet; create one first.")
        owner_id = owner.id
    result = DeviceService(connection.SessionLocal, pki, PairingManager()).enrol_local(name, owner_id)
    bundle = {"host": config.bind_address, "port": config.port, "ca_pem": pki.ca_pem().decode(), "cert_pem": result.cert_pem,
              "key_pem": result.key_pem, "token": result.token, "device_name": result.name}
    out.write_text(json.dumps(bundle), encoding="utf-8")
    print(f"Wrote {out}. It holds this device's private key: import it on the PC, then delete the file.")
    return 0
