"""Manual and pre-migration SQLite backups (CLAUDE.md: "backup before
migrations", "implement restore testing").

Uses sqlite3's own online backup API (Connection.backup()) rather than a
raw file copy. The live database runs in WAL mode (see connection.py's
PRAGMA listener), so recent commits can still be sitting in a separate
-wal file rather than the main .db file at the moment of copying; a
plain file copy of just the .db file can silently produce a backup
missing the most recent transactions. The backup API reads a
transactionally consistent snapshot regardless of WAL state.
"""

import os
import shutil
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Tuple


def _backups_dir(db_path: str) -> str:
    backups_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    os.makedirs(backups_dir, exist_ok=True)
    return backups_dir


def copy_backup_to(backup_path: str, destination_dir: str) -> str:
    """Copy an existing backup to another location - a USB stick, a network
    share, anywhere that is not this disk.

    This is the single largest data-loss exposure in the product. Every
    backup the app takes lands next to the database, which protects against
    software failure and not at all against the thing that actually
    destroys a forecourt PC: a dead drive, a theft, a fire, or ransomware.
    For an offline product with no cloud replica, an off-device copy is the
    only real protection there is.

    A plain file copy is correct HERE, unlike when creating a backup: the
    source is an already-consistent, already-integrity-checked snapshot
    that nothing is writing to, so none of the reasons create_backup uses
    SQLite's online backup API apply.
    """
    if not os.path.exists(backup_path):
        raise IOError(f"Backup file no longer exists: {backup_path}")
    os.makedirs(destination_dir, exist_ok=True)
    destination = os.path.join(destination_dir, os.path.basename(backup_path))
    shutil.copy2(backup_path, destination)

    # Verify the copy actually arrived intact rather than trusting that the
    # write succeeded - a failing USB stick can accept a copy and return a
    # corrupt file, which is exactly the moment this matters.
    is_ok, messages = run_integrity_check(destination)
    if not is_ok:
        raise IOError(f"The copied backup failed its integrity check: {'; '.join(messages)}")
    return destination


def latest_offsite_copy_age_days(backup_path_or_dir: str) -> Optional[float]:
    """How many days since the newest file in an off-device backup folder,
    or None if the folder is unreachable or empty.

    Used to nag rather than to schedule. A pump has no IT staff and the
    machine is not guaranteed to be running at any particular time, so a
    visible warning that the last off-device copy is stale beats a
    scheduler that silently never fires.
    """
    try:
        if not os.path.isdir(backup_path_or_dir):
            return None
        newest = max(
            (os.path.getmtime(os.path.join(backup_path_or_dir, f))
             for f in os.listdir(backup_path_or_dir) if f.endswith(".db")),
            default=None,
        )
    except OSError:
        # An unplugged USB drive or an unreachable share is not an error
        # worth crashing on; it is the very condition being reported.
        return None
    if newest is None:
        return None
    return (datetime.now().timestamp() - newest) / 86400.0


def _backup_filename(reason: str) -> str:
    # Microsecond resolution: two backups (e.g. a manual one right before
    # a restore's own safety backup) can otherwise land in the same
    # second and silently overwrite each other on disk.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_reason = re.sub(r"[^a-z0-9_]+", "_", reason.lower()).strip("_") or "manual"
    return f"petrol_pump_{timestamp}_{safe_reason}.db"


def run_integrity_check(db_path: str) -> Tuple[bool, List[str]]:
    """SQLite's own `PRAGMA integrity_check` (CLAUDE.md: "Implement
    database integrity checks"). Returns (True, ["ok"]) when the file is
    sound, or (False, <problem descriptions>) otherwise - checked
    against a fresh connection so it reflects what's actually on disk,
    not just what the running app's engine currently has cached."""

    connection = sqlite3.connect(db_path)
    try:
        try:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.DatabaseError as exc:
            # A file that isn't a SQLite database at all (truncated,
            # overwritten, wrong format) raises here rather than
            # returning check rows - still a real integrity problem,
            # not a crash the caller should have to guard against.
            return False, [str(exc)]
    finally:
        connection.close()

    messages = [row[0] for row in rows]
    is_ok = messages == ["ok"]
    return is_ok, messages


def create_backup(db_path: str, reason: str = "manual") -> str:
    """Snapshot the live database and return the new backup file's path.

    Verified immediately after creation (CLAUDE.md: "Implement backup
    verification") by running an integrity check against the backup
    file itself, not just trusting that the SQLite backup API succeeded
    - a corrupt backup is only useless the moment someone actually needs
    to restore from it, so it's better to find out now.
    """
    backup_path = os.path.join(_backups_dir(db_path), _backup_filename(reason))
    source = sqlite3.connect(db_path)
    try:
        dest = sqlite3.connect(backup_path)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()

    is_ok, messages = run_integrity_check(backup_path)
    if not is_ok:
        raise OSError(f"Backup verification failed for {backup_path}: {'; '.join(messages)}")

    return backup_path


@dataclass
class BackupInfo:
    path: str
    filename: str
    size_bytes: int
    created_at: datetime


def list_backups(db_path: str) -> List[BackupInfo]:
    backups_dir = _backups_dir(db_path)
    entries = []
    for filename in os.listdir(backups_dir):
        if not filename.endswith(".db"):
            continue
        full_path = os.path.join(backups_dir, filename)
        stat = os.stat(full_path)
        entries.append(
            BackupInfo(
                path=full_path,
                filename=filename,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    return sorted(entries, key=lambda backup: backup.created_at, reverse=True)


def should_take_scheduled_backup(db_path: str, interval_hours: float) -> bool:
    """True when no backup exists yet, or the most recent one (of any
    reason) is older than interval_hours - used to decide whether to
    take an automatic backup on app startup (CLAUDE.md: "Implement
    automatic scheduled backups"). A desktop app that isn't always
    running can't rely on a background scheduler firing at a fixed
    time of day, so "due" is checked relative to the last backup taken,
    whenever that was."""

    backups = list_backups(db_path)
    if not backups:
        return True
    return backups[0].created_at < datetime.now() - timedelta(hours=interval_hours)


def restore_backup(backup_path: str, db_path: str) -> None:
    """Overwrite the live database file's contents with a backup's.

    This only touches the file on disk. A process that already holds the
    live database open (the running application's own SQLAlchemy engine,
    in particular) keeps its existing connections and in-memory state
    afterward — callers driving this from a running app must restart the
    process for the restored data to actually take effect everywhere.
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    source = sqlite3.connect(backup_path)
    try:
        dest = sqlite3.connect(db_path)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
