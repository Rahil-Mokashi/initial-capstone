"""Behaviour of the Main PC once a device is connected: sign-in through a device, the owner's Devices screen, floods, headers,
and the one-writer lock that keeps the audit hash chain a single line."""

import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api_helpers import PASSWORD, audit_chain_ok, audit_events
from lan_helpers import MainPc, make_config
from api.lan.pki import InsecureTestProtector


def sign_in(c: httpx.Client, username: str) -> dict:
    r = c.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_sign_in_through_a_device_is_audited_with_the_device_name_and_address(main_pc, device, session_factory):
    with main_pc.client(device) as c:
        sign_in(c, "manager1")
    events = audit_events(session_factory, "login_success")
    assert events and events[-1].device_info == "Counter PC (127.0.0.1)"


def test_sign_in_floods_are_stopped_and_audited_once(main_pc, device, session_factory):
    with main_pc.client(device) as c:
        codes = [c.post("/api/auth/login", json={"username": "manager1", "password": "wrong-password"}).status_code for _ in range(14)]
    assert codes.count(401) == 10 and codes.count(429) == 4
    import time

    time.sleep(0.5)  # the audit entry is written off the request path
    assert len(audit_events(session_factory, "lan_blocked_login_rate")) == 1
    assert audit_chain_ok(session_factory)


def test_unknown_devices_are_refused_audited_once_and_never_see_a_stack_trace(main_pc, device, session_factory):
    import time

    with main_pc.client(device, with_token=False) as c:
        replies = [c.get("/api/tanks") for _ in range(5)]
    assert {r.status_code for r in replies} == {401}
    assert "Traceback" not in replies[0].text and "File \"" not in replies[0].text
    time.sleep(0.5)
    assert len(audit_events(session_factory, "lan_blocked_device")) == 1


def test_security_headers_and_no_cross_origin_access(main_pc, device):
    with main_pc.client(device) as c:
        r = c.get("/api/health")
        assert r.headers["strict-transport-security"].startswith("max-age=")
        assert r.headers["x-content-type-options"] == "nosniff" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
        pre = c.options("/api/health", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in pre.headers
        assert "access-control-allow-origin" not in c.get("/api/health", headers={"Origin": "http://evil.example"}).headers


def test_the_users_own_permissions_still_decide_what_a_device_may_do(main_pc, device):
    with main_pc.client(device) as c:
        attendant = sign_in(c, "attendant1")
        assert c.get("/api/devices", headers=attendant).status_code == 403
        assert c.get("/api/audit", headers=attendant).status_code in (403, 404)


def test_owner_adds_lists_and_removes_a_device_from_the_devices_screen(main_pc, device, session_factory):
    with main_pc.client(device) as c:
        owner = sign_in(c, "owner1")
        pairing = c.post("/api/devices/pairing", headers=owner)
        assert pairing.status_code == 200
        body = pairing.json()
        assert body["pairing_port"] == main_pc.config.pairing_port and len(body["code"].replace("-", "")) == 10
        assert body["ca_fingerprint"] == main_pc.pki.ca_fingerprint()
        second = main_pc.enrol("Office PC", body["code"])
        assert second["status"] == 200
        names = {d["name"]: d for d in c.get("/api/devices", headers=owner).json()}
        assert set(names) == {"Counter PC", "Office PC"} and names["Office PC"]["revoked_at"] is None
        gone = c.post(f"/api/devices/{names['Office PC']['id']}/revoke", headers=owner, json={"reason": "Replaced"})
        assert gone.status_code == 200 and gone.json()["revoke_reason"] == "Replaced"
    with main_pc.client(second) as other:
        assert other.get("/api/health").status_code == 401
    assert audit_events(session_factory, "pairing_code_created") and audit_events(session_factory, "device_revoked")
    assert audit_chain_ok(session_factory)


def test_devices_endpoints_do_not_exist_in_single_pc_mode(session_factory, users):
    app = create_app("s3cret", session_factory=session_factory, session_timeout_hours=8)
    with TestClient(app, base_url="http://127.0.0.1", headers={"X-Launch-Secret": "s3cret"}) as c:
        token = c.post("/api/auth/login", json={"username": "owner1", "password": PASSWORD}).json()["token"]
        r = c.get("/api/devices", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404
        assert c.post("/api/system/shutdown").status_code == 202  # Single PC mode keeps today's behaviour


def test_console_enrolment_gives_the_main_pcs_own_window_a_device(main_pc, owner_id, session_factory):
    result = main_pc.lan.devices.enrol_local("Main PC window", owner_id)
    bundle = {"ca_pem": main_pc.pki.ca_pem().decode(), "cert_pem": result.cert_pem, "key_pem": result.key_pem, "token": result.token}
    with main_pc.client(bundle) as c:
        assert c.get("/api/health").status_code == 200
    assert audit_events(session_factory, "device_enrolled_by_console")


def test_concurrent_writers_keep_the_audit_hash_chain_unbroken(main_pc, session_factory):
    from app.repositories.audit_log_repository import AuditLogRepository

    errors: list[Exception] = []

    def writer(n: int) -> None:
        try:
            for i in range(12):
                with session_factory() as db:
                    AuditLogRepository(db).record("load_test", description=f"writer {n} entry {i}")
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:2]
    assert len(audit_events(session_factory, "load_test")) == 96
    assert audit_chain_ok(session_factory)
