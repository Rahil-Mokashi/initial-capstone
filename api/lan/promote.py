"""Restore-and-promote: turn the newest backup into a working Main PC database on a replacement computer.

    pperp_api.exe lan promote --backup <file> [--db <target database path>]

It (1) refuses a backup that is not a sound database, (2) puts it in place using the EXISTING restore routine (which keeps a safety
copy of whatever was there), (3) brings the schema up to the current version, (4) verifies the audit chain and counts what it restored,
and prints that summary. The new Main PC then runs `lan init` (a NEW private authority) and every PC is paired again from the Devices
screen: the old authority's keys belonged to the old computer and are not carried over on purpose. See docs/MAIN_PC_RUNBOOK.md.
"""

import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.database import backup as backup_module
from app.database import migrations


class PromoteError(Exception):
    pass


@dataclass
class PromoteResult:
    db_path: str
    users: int
    shifts: int
    audit_entries: int
    audit_chain_ok: bool
    problems: list


def promote(backup_path: str, db_path: str, passphrase: str = "") -> PromoteResult:
    if not os.path.exists(backup_path):
        raise PromoteError(f"Backup not found: {backup_path}")
    if backup_path.endswith(".enc"):  # an encrypted off-device copy
        from api.lan.backup_crypto import BackupCryptoError, decrypt_file

        with tempfile.TemporaryDirectory() as tmp:
            plain = os.path.join(tmp, "backup.db")
            try:
                decrypt_file(backup_path, plain, passphrase)
            except BackupCryptoError as exc:
                raise PromoteError(str(exc)) from None
            return promote(plain, db_path)
    ok, messages = backup_module.run_integrity_check(backup_path)
    if not ok:
        raise PromoteError("That backup is damaged and was not used: " + "; ".join(messages))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if not os.path.exists(db_path):
        sqlite3.connect(db_path).close()  # restore_backup copies INTO an existing file
    backup_module.restore_backup(backup_path, db_path)
    if migrations.current_revision(db_path) is not None:  # a database made by the application always has one
        migrations.upgrade_to_head(db_path)  # a backup from an older version is brought up to date (the verified backup itself is the safety copy)
    ok, messages = backup_module.run_integrity_check(db_path)
    if not ok:
        raise PromoteError("The restored database failed its check: " + "; ".join(messages))

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.repositories.audit_log_repository import AuditLogRepository

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with sessionmaker(bind=engine)() as session:
            chain_ok, problems = AuditLogRepository(session).verify_chain()
            count = lambda table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0  # noqa: E731 - fixed names
            return PromoteResult(db_path, count("users"), count("shifts"), count("audit_logs"), chain_ok, problems[:5])
    finally:
        engine.dispose()
