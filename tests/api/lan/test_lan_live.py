"""Live data on the Main PC: two PCs editing one record, pushes when somebody saves, and reconnecting."""

import json
import threading
import time

import httpx
import pytest

from api.lan import live
from api_helpers import PASSWORD, audit_chain_ok


def sign_in(c: httpx.Client, username: str) -> dict:
    r = c.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def two_pcs(main_pc, owner_id):
    """Two enrolled devices (an office PC and a counter PC) talking to the same Main PC."""
    clients = []
    for name in ("Office PC", "Counter PC"):
        code, _ = main_pc.lan.start_pairing(owner_id)
        clients.append(main_pc.client(main_pc.enrol(name, code)))
    yield clients
    for c in clients:
        c.close()


# ---- two people editing one record ---------------------------------------------------------------------------------------
def test_a_record_read_carries_its_version_and_a_change_counts_up(two_pcs, employee_id):
    a, _ = two_pcs
    owner = sign_in(a, "owner1")
    first = a.get(f"/api/employees/{employee_id}", headers=owner)
    assert first.headers["etag"] == '"0"'
    ok = a.patch(f"/api/employees/{employee_id}", headers={**owner, "If-Match": first.headers["etag"]}, json={"designation": "Cashier"})
    assert ok.status_code == 200 and ok.headers["etag"] == '"1"'
    assert a.get(f"/api/employees/{employee_id}", headers=owner).headers["etag"] == '"1"'


def test_the_second_person_to_save_is_told_who_changed_it_and_when_and_nothing_is_overwritten(two_pcs, employee_id, session_factory):
    a, b = two_pcs
    owner_a, manager_b = sign_in(a, "owner1"), sign_in(b, "manager1")
    seen_a = a.get(f"/api/employees/{employee_id}", headers=owner_a).headers["etag"]
    seen_b = b.get(f"/api/employees/{employee_id}", headers=manager_b).headers["etag"]
    assert a.patch(f"/api/employees/{employee_id}", headers={**owner_a, "If-Match": seen_a}, json={"designation": "Head cashier"}).status_code == 200
    stale = b.patch(f"/api/employees/{employee_id}", headers={**manager_b, "If-Match": seen_b}, json={"designation": "Pump boy"})
    assert stale.status_code == 409
    error = stale.json()["error"]
    assert error["code"] == "conflict_stale" and error["details"]["changed_by"] == "Owner1 Tester"
    assert error["message"].startswith("Changed by Owner1 Tester at ") and len(error["details"]["changed_at"]) == 5  # HH:MM
    # reload, change again: accepted
    fresh = b.get(f"/api/employees/{employee_id}", headers=manager_b)
    assert fresh.json()["designation"] == "Head cashier"  # their work was not lost
    again = b.patch(f"/api/employees/{employee_id}", headers={**manager_b, "If-Match": fresh.headers["etag"]}, json={"designation": "Pump boy"})
    assert again.status_code == 200
    assert audit_chain_ok(session_factory)


def test_two_saves_at_the_same_moment_from_the_same_version_let_exactly_one_through(two_pcs, employee_id):
    a, b = two_pcs
    owner_a, owner_b = sign_in(a, "owner1"), sign_in(b, "manager1")
    tag = a.get(f"/api/employees/{employee_id}", headers=owner_a).headers["etag"]
    results = []

    def save(client, headers, title):
        results.append(client.patch(f"/api/employees/{employee_id}", headers={**headers, "If-Match": tag}, json={"designation": title}).status_code)

    threads = [threading.Thread(target=save, args=(a, owner_a, "A")), threading.Thread(target=save, args=(b, owner_b, "B"))]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 409]


def test_a_save_that_names_no_version_is_still_accepted_and_counted(two_pcs, employee_id):
    a, _ = two_pcs
    owner = sign_in(a, "owner1")
    assert a.patch(f"/api/employees/{employee_id}", headers=owner, json={"designation": "X"}).status_code == 200
    assert a.get(f"/api/employees/{employee_id}", headers=owner).headers["etag"] == '"1"'


def test_a_failed_save_does_not_count_as_a_change(two_pcs, employee_id):
    a, _ = two_pcs
    owner = sign_in(a, "owner1")
    assert a.patch(f"/api/employees/{employee_id}", headers=owner, json={"designation": 5}).status_code == 422
    assert a.get(f"/api/employees/{employee_id}", headers=owner).headers["etag"] == '"0"'


# ---- live pushes -------------------------------------------------------------------------------------------------------------
def read_events(client: httpx.Client, headers: dict, into: list, stop: threading.Event) -> None:
    with client.stream("GET", "/api/events", headers=headers, timeout=None) as r:
        into.append(("status", r.status_code))
        for line in r.iter_lines():
            if line.startswith("data:"):
                into.append(("data", json.loads(line[5:])))
            elif line.startswith(":"):
                into.append(("beat", line))
            if stop.is_set():
                return


def wait_for(predicate, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_everyone_hears_when_somebody_saves(two_pcs, employee_id, monkeypatch):
    monkeypatch.setattr(live, "HEARTBEAT_SECONDS", 0.4)
    a, b = two_pcs
    owner_a, manager_b = sign_in(a, "owner1"), sign_in(b, "manager1")
    heard, stop = [], threading.Event()
    reader = threading.Thread(target=read_events, args=(b, manager_b, heard, stop), daemon=True)
    reader.start()
    assert wait_for(lambda: ("data", {"type": "hello"}) in heard)
    assert heard[0] == ("status", 200)
    a.patch(f"/api/employees/{employee_id}", headers=owner_a, json={"designation": "Cashier"})
    assert wait_for(lambda: ("data", {"type": "changed", "area": "employees", "id": employee_id}) in heard)
    assert wait_for(lambda: any(kind == "beat" for kind, _ in heard))  # the stream stays alive when nothing happens
    stop.set()


def test_signing_in_and_reading_are_not_news(two_pcs, employee_id, main_pc):
    a, b = two_pcs
    owner_a, manager_b = sign_in(a, "owner1"), sign_in(b, "manager1")
    heard, stop = [], threading.Event()
    threading.Thread(target=read_events, args=(b, manager_b, heard, stop), daemon=True).start()
    assert wait_for(lambda: ("data", {"type": "hello"}) in heard)
    a.get(f"/api/employees/{employee_id}", headers=owner_a)
    sign_in(a, "accountant1")
    time.sleep(0.6)
    assert [d for k, d in heard if k == "data" and d.get("type") == "changed"] == []
    stop.set()


def test_a_closed_stream_is_forgotten_and_a_new_one_can_open(two_pcs, main_pc):
    a, _ = two_pcs
    owner = sign_in(a, "owner1")
    hub = main_pc.app.app.hub
    before = hub.subscribers
    with a.stream("GET", "/api/events", headers=owner) as r:
        assert r.status_code == 200
        assert wait_for(lambda: hub.subscribers == before + 1)
    assert wait_for(lambda: hub.subscribers == before)


def test_the_stream_needs_an_enrolled_device(main_pc, device):
    with main_pc.client(device, with_token=False) as c:
        assert c.get("/api/events").status_code == 401


# ---- many PCs at once ---------------------------------------------------------------------------------------------------------
def test_sixteen_pcs_work_at_the_same_time_without_a_lost_save_or_a_broken_audit_chain(main_pc, owner_id, session_factory):
    from api_helpers import audit_events

    clients = []
    for n in range(16):
        result = main_pc.lan.devices.enrol_local(f"PC {n + 1}", owner_id)
        clients.append(main_pc.client({"ca_pem": main_pc.pki.ca_pem().decode(), "cert_pem": result.cert_pem, "key_pem": result.key_pem, "token": result.token}))
        clients[-1].timeout = httpx.Timeout(120)  # password hashing is deliberately slow; a busy test machine must not fail this
    outcomes, lock = [], threading.Lock()

    def work(n: int, client: httpx.Client) -> None:
        user = ("manager1", "accountant1", "owner1", "dataentry1")[n % 4]
        try:
            headers = sign_in(client, user)
            for _ in range(4):
                ok = client.get("/api/tanks", headers=headers).status_code == 200
                with lock:
                    outcomes.append(ok)
            made = client.post("/api/dispensers", headers=sign_in(client, "manager1"), json={"code": f"LOAD-{n + 1}"})
            with lock:
                outcomes.append(True if made.status_code == 201 else f"{made.status_code} {made.text[:150]}")
        except Exception as exc:  # noqa: BLE001
            with lock:
                outcomes.append(repr(exc))

    started = time.time()
    threads = [threading.Thread(target=work, args=(n, c)) for n, c in enumerate(clients)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    [c.close() for c in clients]
    assert outcomes.count(True) == 16 * 5, [o for o in outcomes if o is not True][:3]
    assert len(audit_events(session_factory, "dispenser_created") or audit_events(session_factory, "login_success")) >= 16
    assert audit_chain_ok(session_factory)
