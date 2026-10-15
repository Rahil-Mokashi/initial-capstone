"""The Main PC's safety checks and the "System health" picture (LAN build, Phase 7).

It adds no backup logic: backups, the integrity check and the off-device copy are the existing ones (app/database/backup.py through
BackupService); this only runs them on a schedule, records each outcome (HealthRun, append-only), and reads the state back as a short
list an owner can understand: Good, Look, or Problem, each with one sentence and a time.
"""

import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from app.core.constants import Permission
from app.core.permissions import require_permission
from app.database import backup as backup_module
from app.models.health_run import HealthRun
from app.models.lan_device import LanDevice

STARTED = time.time()
ONLINE_WITHIN = timedelta(minutes=5)
LOW_DISK_BYTES = 5 * 1024**3


def parse_bitlocker(output: str) -> str:
    """'on' | 'off' | 'unknown' from the text of `manage-bde -status <drive>`."""
    text = output.lower()
    if "protection on" in text:
        return "on"
    if "protection off" in text or "fully decrypted" in text:
        return "off"
    return "unknown"


def probe_bitlocker(path: str) -> str:
    """Ask Windows whether the drive holding `path` is encrypted. Needs administrator rights (the Main PC runs as SYSTEM); 'unknown' otherwise."""
    import subprocess
    import sys

    if sys.platform != "win32":
        return "unknown"
    drive = os.path.splitdrive(os.path.abspath(path))[0] or "C:"
    try:
        done = subprocess.run(["manage-bde", "-status", drive], capture_output=True, text=True, timeout=15)
        return parse_bitlocker(done.stdout)
    except Exception:  # noqa: BLE001
        return "unknown"


@dataclass
class HealthRow:
    key: str
    name: str
    state: str  # good | look | problem
    detail: str
    at: Optional[datetime] = None


class SystemHealthService:
    def __init__(self, session, db_path: str, settings, audit_repo, backup_service, auth_service,
                 mail_status: Callable[[], Optional[dict]] = lambda: None, offsite_dir: Callable[[], str] = lambda: "",
                 passphrase: Callable[[], Optional[str]] = lambda: None, encryption_probe: Optional[Callable[[str], str]] = None):
        self._session = session
        self._db_path = db_path
        self._settings = settings
        self._audit_repo = audit_repo
        self._backups = backup_service
        self._auth_service = auth_service
        self._mail_status = mail_status
        self._offsite_dir = offsite_dir
        self._passphrase = passphrase
        self._encryption_probe = encryption_probe

    # ---- the jobs (also called by the scheduler; they never raise)
    def _record(self, kind: str, ok: bool, detail: str) -> bool:
        self._session.add(HealthRun(kind=kind, ok=ok, detail=detail[:300]))
        self._session.commit()
        if not ok:
            self._audit_repo.record(event_type=f"health_{kind}_failed", description=detail[:300])
        return ok

    def run_integrity(self) -> bool:
        try:
            ok, messages = backup_module.run_integrity_check(self._db_path)
            return self._record("integrity", ok, "The database file is sound." if ok else "; ".join(messages))
        except Exception as exc:  # noqa: BLE001
            return self._record("integrity", False, f"Could not check: {exc}")

    def run_audit_chain(self) -> bool:
        from app.repositories.audit_log_repository import AuditLogRepository

        try:
            ok, problems = AuditLogRepository(self._session).verify_chain()
            return self._record("audit_chain", ok, "The audit log is unbroken." if ok else f"{len(problems)} problem(s): {problems[0]}")
        except Exception as exc:  # noqa: BLE001
            return self._record("audit_chain", False, f"Could not verify: {exc}")

    def run_backup_if_due(self) -> bool:
        """The existing rule (`should_take_scheduled_backup`) decides; the existing service takes the backup."""
        hours = float(self._settings.get("backup_interval_hours"))
        try:
            if not backup_module.should_take_scheduled_backup(self._db_path, hours):
                return False
            info = self._backups.create_backup.__wrapped__(self._backups, None)
            return self._record("backup", True, f"Backup {info.filename} taken and verified.")
        except Exception as exc:  # noqa: BLE001
            return self._record("backup", False, f"Backup failed: {exc}")

    def run_offsite(self) -> bool:
        folder = self._offsite_dir()
        if not folder:
            return False
        try:
            latest = backup_module.list_backups(self._db_path)
            if not latest:
                return False
            secret = self._passphrase()
            if secret:
                from api.lan.backup_crypto import decrypt_file, encrypt_file

                target = os.path.join(folder, latest[0].filename + ".enc")
                if not os.path.exists(target):
                    os.makedirs(folder, exist_ok=True)
                    encrypt_file(latest[0].path, target, secret)
                    check = target + ".verify"
                    try:  # prove the copy can be read back before calling it a backup
                        decrypt_file(target, check, secret)
                        ok, messages = backup_module.run_integrity_check(check)
                        if not ok:
                            raise OSError("; ".join(messages))
                    finally:
                        if os.path.exists(check):
                            os.remove(check)
                return self._record("offsite", True, f"Copied {latest[0].filename} to {folder}, encrypted.")
            backup_module.copy_backup_to(latest[0].path, folder)
            return self._record("offsite", True, f"Copied {latest[0].filename} to {folder} (NOT encrypted: set a backup passphrase).")
        except Exception as exc:  # noqa: BLE001
            return self._record("offsite", False, f"Copy to {folder} failed: {exc}")

    def run_all(self) -> None:
        self.run_integrity()
        self.run_audit_chain()
        self.run_backup_if_due()
        self.run_offsite()

    # ---- the picture
    def _last(self, kind: str) -> Optional[HealthRun]:
        return self._session.query(HealthRun).filter_by(kind=kind).order_by(HealthRun.at.desc()).first()

    def backup_age_hours(self) -> Optional[float]:
        backups = backup_module.list_backups(self._db_path)
        if not backups:
            return None
        return (datetime.now() - backups[0].created_at).total_seconds() / 3600

    @require_permission(Permission.SYSTEM_HEALTH_VIEW.value)
    def snapshot(self, actor_user_id: str) -> List[HealthRow]:
        rows: List[HealthRow] = []
        limit = float(self._settings.get("backup_max_age_hours"))
        age = self.backup_age_hours()
        if age is None:
            rows.append(HealthRow("backup", "Latest backup", "problem", "No backup has been taken yet."))
        else:
            state = "good" if age <= limit else ("look" if age <= 2 * limit else "problem")
            rows.append(HealthRow("backup", "Latest backup", state, f"{age:.0f} hours ago (it should be under {limit:.0f})."))
        for kind, name, never in (
            ("integrity", "Database integrity", "Not checked yet: the nightly check has not run."),
            ("audit_chain", "Audit log", "Not verified yet: the nightly check has not run."),
        ):
            run = self._last(kind)
            rows.append(
                HealthRow(kind, name, "look" if run is None else ("good" if run.ok else "problem"), never if run is None else run.detail, run.at if run else None)
            )
        folder = self._offsite_dir()
        run = self._last("offsite")
        if not folder:
            rows.append(HealthRow("offsite", "Copy off this PC", "look", "No USB or network folder is set up for a second copy. A backup on the same disk is lost with the disk."))
        else:
            plain = run is not None and run.ok and "NOT encrypted" in (run.detail or "")
            rows.append(HealthRow("offsite", "Copy off this PC", "look" if run is None or plain else ("good" if run.ok else "problem"),
                                  "Not copied yet." if run is None else run.detail, run.at if run else None))
        free = shutil.disk_usage(os.path.dirname(os.path.abspath(self._db_path))).free
        rows.append(HealthRow("disk", "Free space", "good" if free >= LOW_DISK_BYTES else "problem", f"{free / 1024**3:.1f} GB free where the data lives."))
        if self._encryption_probe is not None:
            enc = self._encryption_probe(self._db_path)
            rows.append(HealthRow(
                "bitlocker", "Disk encryption", {"on": "good", "off": "problem"}.get(enc, "look"),
                {"on": "BitLocker is on for the drive that holds the database.",
                 "off": "BitLocker is OFF. If this PC or its disk is stolen, the data can be read. Turn BitLocker on for this drive.",
                 "unknown": "Could not tell whether BitLocker is on. Check it in Windows (Manage BitLocker); it should be on for the drive that holds the database."}[enc]))
        now = datetime.now(timezone.utc)
        devices = self._session.query(LanDevice).filter(LanDevice.revoked_at.is_(None)).all()
        online = [d for d in devices if d.last_seen_at and (d.last_seen_at.replace(tzinfo=timezone.utc) if d.last_seen_at.tzinfo is None else d.last_seen_at) >= now - ONLINE_WITHIN]
        rows.append(HealthRow("devices", "PCs", "good", f"{len(online)} of {len(devices)} enrolled PCs were seen in the last 5 minutes."))
        mail = self._mail_status()
        if mail and mail.get("enabled"):
            bad = bool(mail.get("problems")) or any(r.status in ("gave_up",) for r in mail.get("outbox", []))
            rows.append(HealthRow("mail", "Email summary", "look" if bad else "good", "; ".join(mail["problems"]) or ("A summary could not be sent; see Email summary." if bad else "Working."), mail.get("last_sent")))
        rows.append(HealthRow("uptime", "Main PC program", "good", f"Running for {int((time.time() - STARTED) // 3600)} hours."))
        return rows
