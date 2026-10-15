"""Scheduled backups, the nightly safety checks, the System health screen, encrypted off-device copies, and restore-and-promote."""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from api.lan.backup_crypto import BackupCryptoError, decrypt_file, encrypt_file
from api.lan.backup_scheduler import BackupScheduler
from api.lan.pki import InsecureTestProtector
from api.lan.promote import PromoteError, promote
from api.lan.secrets_store import SecretStore
from api.services import Services
from api_helpers import audit_chain_ok, audit_events
from app.database import backup as backup_module
from pump_day import TODAY


@pytest.fixture()
def real_db(tmp_path, session_factory, monkeypatch):
    path = str(tmp_path / "api_test.db")
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    return path


@pytest.fixture()
def store(tmp_path, client):
    s = SecretStore(tmp_path / "secrets", InsecureTestProtector(), allow_insecure=True)
    client.app.state.secrets = s
    return s


def rows(client, h):
    return {r["key"]: r for r in client.get("/api/system/health", headers=h).json()}


def scheduler(session_factory, store, when):
    def make():
        db = session_factory()
        return Services(db, 8, secrets=store), db.close

    return BackupScheduler(make, now=lambda: when)


# ---- the screen --------------------------------------------------------------------------------------------------------
def test_a_new_main_pc_says_plainly_what_is_missing(client, owner, real_db, store):
    r = rows(client, owner)
    assert r["backup"]["state"] == "problem" and "No backup" in r["backup"]["detail"]
    assert r["integrity"]["state"] == "look" and r["audit_chain"]["state"] == "look"
    assert r["offsite"]["state"] == "look" and "same disk" in r["offsite"]["detail"]
    assert r["disk"]["state"] == "good" and r["devices"]["state"] == "good"


def test_only_owners_and_admins_see_system_health(client, accountant, manager, data_entry, attendant, admin, owner, real_db, store):
    for who in (accountant, manager, data_entry, attendant):
        assert client.get("/api/system/health", headers=who).status_code == 403
        assert client.post("/api/system/health/run", headers=who).status_code == 403
    assert client.get("/api/system/health", headers=admin).status_code == 200 and client.get("/api/system/health", headers=owner).status_code == 200


def test_running_the_checks_takes_a_backup_and_records_integrity_and_the_audit_chain(client, owner, real_db, store, session_factory):
    after = {r["key"]: r for r in client.post("/api/system/health/run", headers=owner).json()}
    assert after["backup"]["state"] == "good" and after["integrity"]["state"] == "good" and after["audit_chain"]["state"] == "good"
    assert after["integrity"]["at"] and len(backup_module.list_backups(real_db)) == 1
    client.post("/api/system/health/run", headers=owner)  # a backup that is not due is not taken again
    assert len(backup_module.list_backups(real_db)) == 1
    assert audit_chain_ok(session_factory)


def test_an_old_backup_is_a_look_then_a_problem_and_the_checks_engine_says_so(client, owner, real_db, store):
    client.post("/api/system/health/run", headers=owner)
    newest = backup_module.list_backups(real_db)[0].path
    for hours, state in ((20, "good"), (50, "look"), (100, "problem")):
        old = datetime.now().timestamp() - hours * 3600
        os.utime(newest, (old, old))
        assert rows(client, owner)["backup"]["state"] == state
    client.post("/api/checks/run", headers=owner, json={"day": datetime.now().date().isoformat()})
    found = [c for c in client.get("/api/checks", headers=owner).json()["results"] if c["key"] == "system.backup_is_recent"]
    assert found and found[0]["status"] == "fail" and "hours old (limit 36)" in found[0]["sentence"]


def test_a_damaged_database_file_is_reported_not_swallowed(real_db, tmp_path, session_factory, store):
    from app.services.system_health_service import SystemHealthService

    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a database" * 100)
    db = session_factory()
    services = Services(db, 8, secrets=store)
    health = SystemHealthService(db, str(bad), services.pump_settings, services.audit_repo, services.backups, services.auth)
    assert health.run_integrity() is False
    assert audit_events(session_factory, "health_integrity_failed")


# ---- the scheduler ---------------------------------------------------------------------------------------------------------
def test_the_scheduler_takes_a_due_backup_and_runs_the_nightly_checks_once_a_day(real_db, store, session_factory, client, owner):
    client.put("/api/pump-settings/nightly_check_hour", headers=owner, json={"value": "22"})
    s = scheduler(session_factory, store, datetime.fromisoformat(f"{TODAY}T09:00:00"))
    s.tick()  # a backup is due (none exists), but it is not night yet
    assert len(backup_module.list_backups(real_db)) == 1
    assert rows(client, owner)["integrity"]["state"] == "look"
    night = scheduler(session_factory, store, datetime.fromisoformat(f"{TODAY}T23:30:00"))
    night.tick()
    assert rows(client, owner)["integrity"]["state"] == "good"
    from app.models.health_run import HealthRun

    with session_factory() as db:
        before = db.query(HealthRun).count()
    night.tick()  # already done today
    with session_factory() as db:
        assert db.query(HealthRun).count() == before


# ---- copies that leave the Main PC are encrypted ------------------------------------------------------------------------------
def test_a_backup_passphrase_makes_the_off_device_copy_unreadable_without_it(client, owner, real_db, store, tmp_path, session_factory):
    usb = tmp_path / "usb"
    usb.mkdir()
    client.put("/api/settings", headers=owner, json={"offsite_backup_dir": str(usb)})
    assert client.put("/api/system/backup-passphrase", headers=owner, json={"passphrase": "short"}).status_code == 422
    assert client.put("/api/system/backup-passphrase", headers=owner, json={"passphrase": "correct horse battery"}).status_code == 204
    client.post("/api/system/health/run", headers=owner)
    copies = list(usb.iterdir())
    assert len(copies) == 1 and copies[0].name.endswith(".db.enc")
    blob = copies[0].read_bytes()
    assert b"SQLite format" not in blob and b"users" not in blob and b"owner1" not in blob  # nothing readable
    assert rows(client, owner)["offsite"]["state"] == "good" and "encrypted" in rows(client, owner)["offsite"]["detail"]
    ok = tmp_path / "ok.db"
    decrypt_file(str(copies[0]), str(ok), "correct horse battery")
    assert backup_module.run_integrity_check(str(ok))[0]
    with pytest.raises(BackupCryptoError):
        decrypt_file(str(copies[0]), str(tmp_path / "no.db"), "wrong passphrase!!")
    assert not (tmp_path / "no.db").exists()
    tampered = bytearray(blob)
    tampered[-3] ^= 1
    (tmp_path / "t.enc").write_bytes(bytes(tampered))
    with pytest.raises(BackupCryptoError):
        decrypt_file(str(tmp_path / "t.enc"), str(tmp_path / "t.db"), "correct horse battery")
    assert "correct horse battery" not in Path(real_db).read_bytes().decode("latin1")


def test_without_a_passphrase_the_copy_is_made_but_the_screen_says_it_is_not_encrypted(client, owner, real_db, store, tmp_path):
    usb = tmp_path / "usb"
    usb.mkdir()
    client.put("/api/settings", headers=owner, json={"offsite_backup_dir": str(usb)})
    client.post("/api/system/health/run", headers=owner)
    assert [p.name.endswith(".db") for p in usb.iterdir()] == [True]
    off = rows(client, owner)["offsite"]
    assert off["state"] == "look" and "NOT encrypted" in off["detail"]


def test_an_unreachable_off_device_folder_is_a_problem(client, owner, real_db, store, tmp_path):
    client.put("/api/settings", headers=owner, json={"offsite_backup_dir": str(tmp_path / "missing" / "\0bad")})
    client.post("/api/system/health/run", headers=owner)
    assert rows(client, owner)["offsite"]["state"] == "problem"


# ---- restore and promote ---------------------------------------------------------------------------------------------------------
def test_restore_and_promote_brings_a_replacement_main_pc_up_with_everything_and_an_unbroken_audit_chain(client, owner, real_db, store, tmp_path, session_factory):
    client.post("/api/system/health/run", headers=owner)
    newest = backup_module.list_backups(real_db)[0].path
    target = str(tmp_path / "new-main-pc" / "petrol_pump.db")
    result = promote(newest, target)
    assert result.users >= 6 and result.audit_chain_ok and result.audit_entries > 0
    con = sqlite3.connect(target)
    assert con.execute("SELECT username FROM users WHERE username='owner1'").fetchone() == ("owner1",)
    assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    con.close()


def test_promote_from_an_encrypted_off_device_copy_needs_the_passphrase(real_db, tmp_path, session_factory, client, owner):
    client.post("/api/system/health/run", headers=owner)
    plain = backup_module.list_backups(real_db)[0].path
    enc = str(tmp_path / "copy.db.enc")
    encrypt_file(plain, enc, "a long passphrase here")
    with pytest.raises(PromoteError, match="Wrong passphrase"):
        promote(enc, str(tmp_path / "x" / "p.db"), "nope nope nope nope")
    assert not (tmp_path / "x" / "p.db").exists()
    assert promote(enc, str(tmp_path / "y" / "p.db"), "a long passphrase here").audit_chain_ok


def test_promote_refuses_a_damaged_backup_and_leaves_the_target_alone(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"garbage" * 1000)
    target = tmp_path / "live.db"
    target.write_bytes(b"precious")
    with pytest.raises(PromoteError, match="damaged"):
        promote(str(bad), str(target))
    assert target.read_bytes() == b"precious"


def test_promote_notices_a_tampered_audit_log(client, owner, real_db, store, tmp_path):
    client.post("/api/system/health/run", headers=owner)
    newest = backup_module.list_backups(real_db)[0].path
    tampered = str(tmp_path / "tampered.db")
    shutil.copy(newest, tampered)
    con = sqlite3.connect(tampered)
    con.execute("UPDATE audit_logs SET description = 'edited later' WHERE rowid = (SELECT MIN(rowid) FROM audit_logs WHERE entry_hash IS NOT NULL)")
    con.commit()
    con.close()
    result = promote(tampered, str(tmp_path / "t" / "p.db"))
    assert result.audit_chain_ok is False and result.problems


# ---- disk encryption -------------------------------------------------------------------------------------------------------------
def test_the_bitlocker_text_is_read_correctly_and_unknown_is_never_reported_as_safe():
    from app.services.system_health_service import parse_bitlocker

    assert parse_bitlocker("Conversion Status:    Fully Encrypted\n    Protection Status:    Protection On") == "on"
    assert parse_bitlocker("Conversion Status:    Fully Decrypted\n    Protection Status:    Protection Off") == "off"
    assert parse_bitlocker("ERROR: An attempt to access the BitLocker driver failed") == "unknown"


def test_the_screen_shows_disk_encryption_on_a_main_pc_and_calls_off_a_problem(client, owner, real_db, store, monkeypatch):
    import app.services.system_health_service as m

    monkeypatch.setattr(m, "probe_bitlocker", lambda path: "off")
    row = rows(client, owner)["bitlocker"]
    assert row["state"] == "problem" and "OFF" in row["detail"]
    monkeypatch.setattr(m, "probe_bitlocker", lambda path: "unknown")
    assert rows(client, owner)["bitlocker"]["state"] == "look"
    monkeypatch.setattr(m, "probe_bitlocker", lambda path: "on")
    assert rows(client, owner)["bitlocker"]["state"] == "good"
