"""Company profile, backups and the audit log."""

import pytest

from api_helpers import audit_chain_ok, audit_events


# ---- settings -------------------------------------------------------------------------------------
def test_settings_start_empty_then_save_and_audit(client, manager, session_factory):
    s = client.get("/api/settings", headers=manager).json()
    assert s["company_name"] is None and s["has_company_profile"] is False
    body = {"company_name": "  Sai Fuels  ", "gst_number": "27aapfu0939f1zv", "phone": "+91 98765 43210", "city": ""}
    saved = client.put("/api/settings", headers=manager, json=body).json()
    assert saved["company_name"] == "Sai Fuels" and saved["gst_number"] == "27AAPFU0939F1ZV"
    assert saved["city"] is None and saved["has_company_profile"] is True
    assert client.get("/api/settings", headers=manager).json()["company_name"] == "Sai Fuels"
    assert len(audit_events(session_factory, "settings_updated")) == 1 and audit_chain_ok(session_factory)


@pytest.mark.parametrize(
    "field,value", [("gst_number", "SHORT"), ("phone", "12"), ("email", "@x.com"), ("company_name", "x" * 201)]
)
def test_settings_validation_names_the_field(client, manager, field, value):
    resp = client.put("/api/settings", headers=manager, json={field: value})
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == field


def test_settings_permissions(client, accountant, attendant):
    assert client.get("/api/settings", headers=accountant).status_code == 200  # settings.view
    assert client.put("/api/settings", headers=accountant, json={"company_name": "X"}).status_code == 403
    assert client.get("/api/settings", headers=attendant).status_code == 200  # attendants hold settings.view too
    assert client.put("/api/settings", headers=attendant, json={"company_name": "X"}).status_code == 403


# ---- backups --------------------------------------------------------------------------------------
@pytest.fixture()
def real_db(tmp_path, session_factory, monkeypatch):
    """BackupService works on the database FILE, so point it at the test one."""
    monkeypatch.setattr("app.database.connection.DB_PATH", str(tmp_path / "api_test.db"))
    return tmp_path


def test_backup_create_list_check(client, admin, real_db, session_factory):
    listing = client.get("/api/backups", headers=admin).json()
    assert listing["backups"] == [] and listing["offsite"]["state"] == "never"
    made = client.post("/api/backups", headers=admin)
    assert made.status_code == 201 and made.json()["filename"].endswith(".db") and made.json()["size_bytes"] > 0
    assert [b["filename"] for b in client.get("/api/backups", headers=admin).json()["backups"]] == [made.json()["filename"]]
    check = client.post("/api/backups/check", headers=admin).json()
    assert check["ok"] is True
    assert len(audit_events(session_factory, "backup_created")) == 1 and audit_chain_ok(session_factory)


def test_backup_is_admin_only_and_unknown_names_are_404(client, admin, manager, real_db):
    assert client.get("/api/backups", headers=manager).status_code == 403
    assert client.post("/api/backups", headers=manager).status_code == 403
    gone = client.post("/api/backups/..%2Fsecret.db/restore", headers=admin, json={})
    assert gone.status_code == 404
    assert client.post("/api/backups/nope.db/copy", headers=admin, json={"destination_dir": "x"}).status_code == 404


def test_copy_offsite_and_staleness_state(client, admin, real_db, tmp_path):
    name = client.post("/api/backups", headers=admin).json()["filename"]
    usb = tmp_path / "usb"
    usb.mkdir()
    out = client.post(f"/api/backups/{name}/copy", headers=admin, json={"destination_dir": str(usb)}).json()
    assert (usb / name).exists() and out["offsite"]["state"] == "ok"
    # the configured folder drives the warning on the list
    client.put("/api/settings", headers=admin, json={"offsite_backup_dir": str(usb)})
    assert client.get("/api/backups", headers=admin).json()["offsite"]["state"] == "ok"
    client.put("/api/settings", headers=admin, json={"offsite_backup_dir": str(tmp_path / "unplugged")})
    assert client.get("/api/backups", headers=admin).json()["offsite"]["state"] == "unreachable"
    assert client.post(f"/api/backups/{name}/copy", headers=admin, json={"destination_dir": "  "}).status_code == 422


def test_restore_without_a_reason_records_the_default(client, admin, real_db, session_factory):
    name = client.post("/api/backups", headers=admin).json()["filename"]
    resp = client.post(f"/api/backups/{name}/restore", headers=admin, json={})
    assert resp.status_code == 204
    events = audit_events(session_factory, "database_restored")
    assert len(events) == 1 and events[0].description == "No reason given"


# ---- audit ----------------------------------------------------------------------------------------
def test_audit_search_filters_and_actor_list(client, manager, admin):
    client.put("/api/settings", headers=manager, json={"company_name": "A"})
    rows = client.get("/api/audit?event_type=settings", headers=manager).json()
    assert rows and all("settings" in r["event_type"] for r in rows) and rows[0]["actor"] == "manager1"
    actors = client.get("/api/audit/actors", headers=manager).json()
    manager_id = next(a["id"] for a in actors if a["username"] == "manager1")
    assert all(r["actor"] == "manager1" for r in client.get(f"/api/audit?actor_id={manager_id}", headers=manager).json())
    assert client.get("/api/audit?date_from=2999-01-01", headers=manager).json() == []
    assert client.get("/api/audit?date_from=not-a-date", headers=manager).status_code == 422


def test_audit_verify_and_permissions(client, manager, attendant, session_factory):
    ok = client.post("/api/audit/verify", headers=manager).json()
    assert ok == {"intact": True, "problems": []}
    assert len(audit_events(session_factory, "audit_trail_verified")) == 1
    for path in ("/api/audit", "/api/audit/actors"):
        assert client.get(path, headers=attendant).status_code == 403
    assert client.post("/api/audit/verify", headers=attendant).status_code == 403


# ---- printed documents carry the company profile (the Qt screens never pass it) -------------------
def test_printed_html_is_headed_with_the_company_profile(client, manager):
    before = client.get("/api/reports/fuel_type_summary", headers=manager)
    assert before.status_code == 200 and "<h2>Petrol Pump ERP</h2>" in before.json()["html"]
    client.put("/api/settings", headers=manager, json={"company_name": "Sai Fuels", "gst_number": "27AAPFU0939F1ZV"})
    after = client.get("/api/reports/fuel_type_summary", headers=manager)
    assert after.status_code == 200
    assert "<h2>Sai Fuels</h2>" in after.json()["html"] and "GSTIN: 27AAPFU0939F1ZV" in after.json()["html"]
