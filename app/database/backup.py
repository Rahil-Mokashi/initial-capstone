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
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple


def _backups_dir(db_path: str) -> str:
    backups_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    os.makedirs(backups_dir, exist_ok=True)
    return backups_dir


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
