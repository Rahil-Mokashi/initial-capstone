"""Backups can be copied off the machine they protect.

Every backup the app takes lands next to the database. That protects
against software failure and not at all against the thing that actually
destroys a forecourt PC: a dead drive, a theft, a fire, or ransomware. For
an offline product with no cloud replica, an off-device copy is the only
real protection there is - which makes this the single largest data-loss
exposure in the product.
"""

import os
import sqlite3

import pytest

from app.database.backup import (
    copy_backup_to,
    latest_offsite_copy_age_days,
    run_integrity_check,
)


@pytest.fixture()
def a_backup(tmp_path):
    """A real, valid SQLite file standing in for a backup."""
    path = tmp_path / "petrol_pump_20260817_backup.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sales (id TEXT PRIMARY KEY, amount NUMERIC)")
    conn.execute("INSERT INTO sales VALUES ('1', 1000.00)")
    conn.commit()
    conn.close()
    return str(path)


def test_a_backup_can_be_copied_to_another_location(a_backup, tmp_path):
    usb = tmp_path / "usb_drive"
    destination = copy_backup_to(a_backup, str(usb))

    assert os.path.exists(destination)
    assert os.path.basename(destination) == os.path.basename(a_backup)


def test_the_copy_is_a_usable_database_not_just_bytes(a_backup, tmp_path):
    """A copy that cannot be opened is not a backup."""
    destination = copy_backup_to(a_backup, str(tmp_path / "usb"))

    conn = sqlite3.connect(destination)
    assert conn.execute("SELECT amount FROM sales").fetchone()[0] == 1000.00
    conn.close()


def test_the_copy_is_integrity_checked_on_arrival(a_backup, tmp_path):
    """A failing USB stick can accept a write and return a corrupt file,
    which is exactly the moment this matters."""
    destination = copy_backup_to(a_backup, str(tmp_path / "usb"))
    is_ok, messages = run_integrity_check(destination)
    assert is_ok, messages


def test_the_destination_folder_is_created_if_missing(a_backup, tmp_path):
    destination = copy_backup_to(a_backup, str(tmp_path / "does" / "not" / "exist"))
    assert os.path.exists(destination)


def test_copying_a_missing_backup_fails_loudly(tmp_path):
    with pytest.raises(IOError):
        copy_backup_to(str(tmp_path / "gone.db"), str(tmp_path / "usb"))


def test_a_corrupt_source_is_rejected_rather_than_silently_copied(tmp_path):
    """Copying a corrupt file to a USB stick and reporting success would be
    worse than failing - the operator would believe they were protected."""
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is not a SQLite database at all")
    with pytest.raises(IOError):
        copy_backup_to(str(broken), str(tmp_path / "usb"))


# ---------------------------------------------------------------------
# The nag: how stale is the off-device copy?
# ---------------------------------------------------------------------

def test_age_is_none_when_the_drive_is_unreachable(tmp_path):
    """An unplugged USB drive is the condition being reported, not a crash."""
    assert latest_offsite_copy_age_days(str(tmp_path / "not_plugged_in")) is None


def test_age_is_none_for_an_empty_destination(tmp_path):
    empty = tmp_path / "usb"
    empty.mkdir()
    assert latest_offsite_copy_age_days(str(empty)) is None


def test_a_fresh_copy_reports_an_age_near_zero(a_backup, tmp_path):
    usb = tmp_path / "usb"
    copy_backup_to(a_backup, str(usb))
    age = latest_offsite_copy_age_days(str(usb))
    assert age is not None
    assert age < 1.0


def test_an_old_copy_reports_its_age(a_backup, tmp_path):
    usb = tmp_path / "usb"
    destination = copy_backup_to(a_backup, str(usb))
    ten_days_ago = os.path.getmtime(destination) - (10 * 86400)
    os.utime(destination, (ten_days_ago, ten_days_ago))

    age = latest_offsite_copy_age_days(str(usb))
    assert 9.5 < age < 10.5
