import sqlite3
import time
from datetime import datetime, timedelta

import pytest

from app.database.backup import (
    BackupInfo,
    create_backup,
    list_backups,
    restore_backup,
    run_integrity_check,
    should_take_scheduled_backup,
)


@pytest.fixture()
def live_db(tmp_path):
    db_path = str(tmp_path / "petrol_pump.db")
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE fuels (id TEXT PRIMARY KEY, fuel_type TEXT)")
    connection.commit()
    connection.close()
    return db_path


def _row_count(db_path: str) -> int:
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute("SELECT COUNT(*) FROM fuels").fetchone()[0]
    finally:
        connection.close()


def test_create_backup_copies_committed_data(live_db):
    connection = sqlite3.connect(live_db)
    connection.execute("INSERT INTO fuels VALUES ('1', 'Petrol')")
    connection.commit()
    connection.close()

    backup_path = create_backup(live_db, reason="manual")

    assert _row_count(backup_path) == 1


def test_create_backup_captures_data_still_sitting_in_the_wal_file(live_db):
    """The whole reason create_backup uses sqlite3's online backup API
    instead of a raw file copy: WAL mode can leave recent commits in a
    separate -wal file rather than the main .db file, and a plain copy
    of just the .db file would silently miss them."""
    connection = sqlite3.connect(live_db)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("INSERT INTO fuels VALUES ('1', 'Diesel')")
    connection.commit()
    # Deliberately no checkpoint - the row may still be sitting in petrol_pump.db-wal.
    connection.close()

    backup_path = create_backup(live_db, reason="manual")

    assert _row_count(backup_path) == 1


def test_create_backup_filename_includes_sanitized_reason(live_db):
    backup_path = create_backup(live_db, reason="Pre Migration!!")
    assert "pre_migration" in backup_path.lower()
    assert backup_path.endswith(".db")


def test_create_backup_places_file_in_backups_subdirectory(live_db, tmp_path):
    backup_path = create_backup(live_db, reason="manual")
    assert str(tmp_path / "backups") in backup_path


def test_list_backups_returns_newest_first(live_db):
    first = create_backup(live_db, reason="manual")
    time.sleep(1.1)  # filesystem mtime resolution on some platforms is ~1s
    second = create_backup(live_db, reason="manual")

    backups = list_backups(live_db)

    assert [b.path for b in backups[:2]] == [second, first]
    assert all(isinstance(b, BackupInfo) for b in backups)
    assert backups[0].size_bytes > 0


def test_restore_backup_overwrites_live_database(live_db):
    connection = sqlite3.connect(live_db)
    connection.execute("INSERT INTO fuels VALUES ('1', 'Petrol')")
    connection.commit()
    connection.close()
    backup_path = create_backup(live_db, reason="manual")

    connection = sqlite3.connect(live_db)
    connection.execute("INSERT INTO fuels VALUES ('2', 'Diesel')")
    connection.commit()
    connection.close()
    assert _row_count(live_db) == 2

    restore_backup(backup_path, live_db)

    assert _row_count(live_db) == 1


def test_restore_backup_raises_for_missing_file(live_db, tmp_path):
    with pytest.raises(FileNotFoundError):
        restore_backup(str(tmp_path / "does-not-exist.db"), live_db)


def test_run_integrity_check_passes_for_a_sound_database(live_db):
    is_ok, messages = run_integrity_check(live_db)
    assert is_ok is True
    assert messages == ["ok"]


def test_run_integrity_check_fails_for_a_corrupted_file(tmp_path):
    corrupt_path = str(tmp_path / "corrupt.db")
    with open(corrupt_path, "wb") as f:
        f.write(b"this is not a valid sqlite file" * 100)

    is_ok, messages = run_integrity_check(corrupt_path)

    assert is_ok is False
    assert messages != ["ok"]


def test_create_backup_verifies_the_new_backup(live_db):
    # A normal backup of a sound live database should pass verification
    # and simply return the path, not raise.
    backup_path = create_backup(live_db, reason="manual")
    is_ok, _ = run_integrity_check(backup_path)
    assert is_ok is True


def test_should_take_scheduled_backup_true_when_none_exist(live_db):
    assert should_take_scheduled_backup(live_db, interval_hours=24) is True


def test_should_take_scheduled_backup_false_right_after_a_backup(live_db):
    create_backup(live_db, reason="manual")
    assert should_take_scheduled_backup(live_db, interval_hours=24) is False


def test_should_take_scheduled_backup_true_once_the_interval_has_passed(live_db):
    import os

    backup_path = create_backup(live_db, reason="manual")
    # Back-date the backup file's mtime (what list_backups reads its
    # created_at from) instead of mocking datetime, so list_backups'
    # own use of datetime.fromtimestamp is unaffected.
    stale_time = (datetime.now() - timedelta(hours=48)).timestamp()
    os.utime(backup_path, (stale_time, stale_time))

    assert should_take_scheduled_backup(live_db, interval_hours=24) is True
