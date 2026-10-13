"""Entered -> Verified -> Approved -> Locked: who may move a shift, what changes it back, and that a locked shift really is locked."""

from datetime import date

from api_helpers import audit_chain_ok, audit_events
from pump_day import TODAY
from test_api_close_desk import _body, _modes, _setup


def _entered(client, data_entry, manager):
    """A shift whose figures were typed on the Close Shift desk."""
    nozzle, shift, tank = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    assert client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, modes)).status_code == 200
    return nozzle, shift, modes


def _status(client, h, shift_id):
    rows = client.get("/api/entries", headers=h).json()
    return next(r["status"] for r in rows if r["shift_id"] == shift_id)


def test_closing_a_shift_enters_it_and_the_chain_runs_in_order(client, data_entry, manager, accountant, owner, session_factory):
    _, shift, _ = _entered(client, data_entry, manager)
    sid = shift["id"]
    assert _status(client, accountant, sid) == "entered"
    # in order only
    assert client.post(f"/api/entries/{sid}/approve", headers=owner).status_code == 409
    assert client.post(f"/api/entries/{sid}/lock", headers=owner).status_code == 409
    assert client.post(f"/api/entries/{sid}/verify", headers=accountant).json()["status"] == "verified"
    assert client.post(f"/api/entries/{sid}/approve", headers=owner).json()["status"] == "approved"
    locked = client.post(f"/api/entries/{sid}/lock", headers=owner).json()
    assert locked["status"] == "locked"
    assert [(e["action"], e["by"]) for e in locked["events"]] == [
        ("entered", "dataentry1"), ("verified", "accountant1"), ("approved", "owner1"), ("locked", "owner1")]
    for event in ("shift_entry_verified", "shift_entry_approved", "shift_entry_locked"):
        assert audit_events(session_factory, event)
    assert audit_chain_ok(session_factory)


def test_only_the_right_roles_may_move_a_shift(client, data_entry, manager, accountant, owner):
    _, shift, _ = _entered(client, data_entry, manager)
    sid = shift["id"]
    assert client.post(f"/api/entries/{sid}/verify", headers=data_entry).status_code == 403
    assert client.post(f"/api/entries/{sid}/verify", headers=manager).status_code == 403
    client.post(f"/api/entries/{sid}/verify", headers=accountant)
    assert client.post(f"/api/entries/{sid}/approve", headers=accountant).status_code == 403  # the accountant verifies, owners approve
    client.post(f"/api/entries/{sid}/approve", headers=owner)
    assert client.post(f"/api/entries/{sid}/lock", headers=accountant).status_code == 403
    assert client.get("/api/entries", headers=data_entry).status_code == 200  # everybody who works on shifts can SEE where they stand


def test_changing_a_figure_after_it_was_verified_sends_it_back_and_says_so(client, data_entry, manager, accountant):
    _, shift, modes = _entered(client, data_entry, manager)
    sid = shift["id"]
    client.post(f"/api/entries/{sid}/verify", headers=accountant)
    fix = client.post(f"/api/close-shift/{sid}", headers=data_entry, json={"modes": [{"tender_id": modes["CARD"], "amount": "10500.00"}]})
    assert fix.status_code == 200
    rows = {r["shift_id"]: r for r in client.get("/api/entries", headers=accountant).json()}
    assert rows[sid]["status"] == "entered"
    assert rows[sid]["events"][-1]["action"] == "data_changed" and rows[sid]["events"][-1]["by"] is None


def test_a_locked_shift_cannot_be_changed_by_anyone_or_any_screen(client, data_entry, manager, accountant, owner, session_factory):
    _, shift, modes = _entered(client, data_entry, manager)
    sid = shift["id"]
    for who, path in ((accountant, "verify"), (owner, "approve"), (owner, "lock")):
        client.post(f"/api/entries/{sid}/{path}", headers=who)
    blocked = client.post(f"/api/close-shift/{sid}", headers=owner, json={"modes": [{"tender_id": modes["CARD"], "amount": "1.00"}]})
    assert blocked.status_code == 409 and "locked" in blocked.json()["error"]["message"]
    # a different door into the same data (a plain sale on that shift) is shut as well
    sale = client.get("/api/sales", headers=manager).json()["items"][0]
    void = client.post(f"/api/sales/{sale["id"]}/cancel", headers=owner, json={"reason": "try"})
    assert void.status_code == 409
    after = client.get(f"/api/close-shift/{sid}", headers=owner).json()
    assert {m["label"]: m["amount"] for m in after["modes"] if m["amount"]} == {"CARD": "10000.00", "PHONE PAY": "5000.00"}  # nothing changed
    assert audit_chain_ok(session_factory)


def test_a_correction_is_an_owner_reopen_with_a_reason_and_then_the_chain_starts_again(client, data_entry, manager, accountant, owner, session_factory):
    _, shift, modes = _entered(client, data_entry, manager)
    sid = shift["id"]
    for who, path in ((accountant, "verify"), (owner, "approve"), (owner, "lock")):
        client.post(f"/api/entries/{sid}/{path}", headers=who)
    assert client.post(f"/api/entries/{sid}/reopen", headers=accountant, json={"reason": "x"}).status_code == 403
    assert client.post(f"/api/entries/{sid}/reopen", headers=owner, json={"reason": "  "}).status_code == 422
    reopened = client.post(f"/api/entries/{sid}/reopen", headers=owner, json={"reason": "Card slip was typed wrong"}).json()
    assert reopened["status"] == "entered" and reopened["events"][-1]["reason"] == "Card slip was typed wrong"
    fixed = client.post(f"/api/close-shift/{sid}", headers=data_entry, json={"modes": [{"tender_id": modes["CARD"], "amount": "11000.00"}]})
    assert fixed.status_code == 200 and fixed.json()["tally"]["status"] == "balanced"
    assert audit_events(session_factory, "shift_entry_reopened")
    assert client.post(f"/api/entries/{sid}/reopen", headers=owner, json={"reason": "again"}).status_code == 409  # already open


def test_owner_choice_v06_two_owners_means_a_different_owner_locks(client, data_entry, manager, accountant, owner, admin, session_factory):
    _, shift, _ = _entered(client, data_entry, manager)
    sid = shift["id"]
    client.put("/api/pump-settings/owner_lock_rule", headers=owner, json={"value": "two_owners"})
    client.post(f"/api/entries/{sid}/verify", headers=accountant)
    client.post(f"/api/entries/{sid}/approve", headers=owner)
    same = client.post(f"/api/entries/{sid}/lock", headers=owner)
    assert same.status_code == 409 and "different owner" in same.json()["error"]["message"]
    assert client.post(f"/api/entries/{sid}/lock", headers=admin).json()["status"] == "locked"


def test_the_checks_say_how_many_entries_wait_for_verification(client, data_entry, manager, accountant, owner):
    _, shift, _ = _entered(client, data_entry, manager)
    client.post("/api/checks/run", headers=owner, json={"day": TODAY})
    rows = [c for c in client.get(f"/api/checks?day={TODAY}", headers=owner).json()["results"] if c["key"] == "workflow.entries_verified"]
    day = date.fromisoformat(TODAY)
    assert rows and rows[0]["status"] == "warn" and rows[0]["sentence"] == f"Day {day.day} {day.strftime('%b')}: 1 entry not yet verified"
    client.post(f"/api/entries/{shift['id']}/verify", headers=accountant)
    client.post("/api/checks/run", headers=owner, json={"day": TODAY})
    rows = [c for c in client.get(f"/api/checks?day={TODAY}", headers=owner).json()["results"] if c["key"] == "workflow.entries_verified"]
    assert rows[0]["status"] == "pass"
