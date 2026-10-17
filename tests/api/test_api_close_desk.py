"""The Close Shift desk: readings + money collected + tally in one go; a preview that saves nothing; all-or-nothing saves."""

from decimal import Decimal

from api_helpers import audit_chain_ok
from pump_day import TODAY

D = Decimal


def _setup(client, h):
    fuels = {f["fuel_type"]: f["id"] for f in client.get("/api/lookups/fuels", headers=h).json()}
    client.post(f"/api/fuel-prices/{fuels['Petrol']}/rate", headers=h, json={"new_rate_per_liter": "100.00"})
    tank = client.post("/api/tanks", headers=h, json={"code": "MS-22", "fuel_id": fuels["Petrol"], "capacity": "50000", "opening_stock": "10000"}).json()
    d = client.post("/api/dispensers", headers=h, json={"code": "D1"}).json()
    nozzle = client.post("/api/nozzles", headers=h, json={"code": "N1", "dispenser_id": d["id"], "fuel_id": fuels["Petrol"], "tank_id": tank["id"]}).json()
    shift = client.post("/api/shifts", headers=h, json={"shift_date": TODAY, "shift_label": "Morning"}).json()
    return nozzle, shift, tank


def _modes(client, h, shift_id):
    return {m["label"]: m["tender_id"] for m in client.get(f"/api/close-shift/{shift_id}", headers=h).json()["modes"]}


def _body(nozzle, modes, card="10000.00", phone="5000.00", advance="20000.00", final="14000.00"):
    return {
        "readings": [{"nozzle_id": nozzle["id"], "opening": "1000.000", "closing": "1505.000", "testing": "5.000"}],
        "modes": [{"tender_id": modes["CARD"], "amount": card}, {"tender_id": modes["PHONE PAY"], "amount": phone}],
        "advance": advance, "final": final,
    }


def test_the_desk_starts_empty_with_the_usual_testing_filled_in(client, data_entry, manager):
    nozzle, shift, _ = _setup(client, manager)
    desk = client.get(f"/api/close-shift/{shift['id']}", headers=data_entry).json()
    assert desk["default_testing"] == "5.000"
    assert [(n["code"], n["opening"], n["closed"]) for n in desk["nozzles"]] == [("N1", None, False)]
    assert {"CARD", "PHONE PAY", "PTM", "DTP Card"} <= {m["label"] for m in desk["modes"]}
    assert desk["cash"] == {"advance": "0.00", "final": "0.00", "recorded": False}
    assert desk["tally"]["status"] == "balanced" and desk["tally"]["total_sale"] == "0.00"


def test_the_tally_shows_a_shortage_while_typing_and_saves_nothing(client, data_entry, manager, session_factory):
    nozzle, shift, tank = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    r = client.post(f"/api/close-shift/{shift['id']}/tally", headers=data_entry, json=_body(nozzle, modes))
    assert r.status_code == 200, r.text
    t = r.json()["tally"]
    # 1505 - 1000 = 505 on the meter, 5 of it was testing that went back into the tank: 500 L sold at 100
    assert t["total_sale"] == "50000.00" and t["collected"] == "49000.00"
    assert t["difference"] == "1000.00" and t["status"] == "short"
    assert [(l["label"], l["amount"]) for l in t["lines"] if l["amount"] != "0.00"] == [("CARD", "10000.00"), ("PHONE PAY", "5000.00"), ("Advance", "20000.00"), ("Final", "14000.00")]
    # ... and nothing was kept
    after = client.get(f"/api/close-shift/{shift['id']}", headers=data_entry).json()
    assert after["nozzles"][0]["closed"] is False and after["cash"]["recorded"] is False
    assert after["tally"]["total_sale"] == "0.00" and all(m["amount"] is None for m in after["modes"] if not m["read_only"])
    assert client.get("/api/sales", headers=manager).json()["items"] == []
    assert D(client.get(f"/api/tanks/{tank['id']}", headers=manager).json()["current_stock"]) == D("10000")
    assert audit_chain_ok(session_factory)


def test_saving_records_everything_and_the_tank_loses_only_what_was_sold(client, data_entry, manager):
    nozzle, shift, tank = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    saved = client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, modes))
    assert saved.status_code == 200, saved.text
    desk = saved.json()
    assert desk["tally"]["status"] == "short" and desk["tally"]["difference"] == "1000.00"
    assert desk["nozzles"][0]["closed"] and desk["cash"] == {"advance": "20000.00", "final": "14000.00", "recorded": True}
    assert {m["label"]: m["amount"] for m in desk["modes"] if m["amount"] and not m["read_only"]} == {"CARD": "10000.00", "PHONE PAY": "5000.00"}
    assert D(client.get(f"/api/tanks/{tank['id']}", headers=manager).json()["current_stock"]) == D("9500")  # 505 metered - 5 testing returned


def test_a_card_total_can_be_retyped_and_the_tally_follows_to_balanced_then_excess(client, data_entry, manager):
    nozzle, shift, _ = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, modes))
    fix = {"modes": [{"tender_id": modes["CARD"], "amount": "11000.00"}]}
    t = client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=fix).json()["tally"]
    assert t["status"] == "balanced" and t["difference"] == "0.00"
    t = client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json={"modes": [{"tender_id": modes["CARD"], "amount": "11250.00"}]}).json()["tally"]
    assert t["status"] == "excess" and t["difference"] == "-250.00"


def test_advance_and_final_are_written_once(client, data_entry, manager):
    nozzle, shift, _ = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, modes))
    same = client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json={"advance": "20000.00", "final": "14000.00"})
    assert same.status_code == 200
    changed = client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json={"advance": "1.00"})
    assert changed.status_code == 409 and "already recorded" in changed.json()["error"]["message"]


def test_a_bad_figure_saves_nothing_at_all(client, data_entry, manager, session_factory):
    nozzle, shift, _ = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    body = _body(nozzle, modes)
    body["modes"].append({"tender_id": "not-a-real-mode", "amount": "5.00"})
    r = client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=body)
    assert r.status_code >= 400
    after = client.get(f"/api/close-shift/{shift['id']}", headers=data_entry).json()
    assert after["nozzles"][0]["closed"] is False and after["cash"]["recorded"] is False and all(m["amount"] is None for m in after["modes"] if not m["read_only"])
    assert client.get("/api/sales", headers=manager).json()["items"] == []
    assert audit_chain_ok(session_factory)


def test_permissions(client, data_entry, manager, attendant, accountant):
    nozzle, shift, _ = _setup(client, manager)
    assert client.get(f"/api/close-shift/{shift['id']}", headers=attendant).status_code == 403
    assert client.post(f"/api/close-shift/{shift['id']}/tally", headers=accountant, json={}).status_code == 403
    assert client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json={}).status_code == 200


def test_saving_the_desk_closes_the_shift_but_the_preview_does_not(client, data_entry, manager):
    nozzle, shift, _ = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    client.post(f"/api/close-shift/{shift['id']}/tally", headers=data_entry, json=_body(nozzle, modes))
    assert client.get(f"/api/shifts/{shift['id']}", headers=manager).json()["status"] == "open"
    r = client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, modes))
    assert r.status_code == 200, r.text
    assert client.get(f"/api/shifts/{shift['id']}", headers=manager).json()["status"] == "closed"
    # a closed shift is corrected by reopening it first, as before
    assert client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, modes)).status_code == 409



def test_a_shift_open_for_more_than_24_hours_fails_a_check(client, manager, owner, session_factory):
    from datetime import datetime, timedelta, timezone

    from app.models.shift import Shift

    nozzle, shift, _ = _setup(client, manager)
    client.post("/api/checks/run", headers=owner, json={})
    row = {r["key"]: r for r in client.get(f"/api/checks?day={TODAY}", headers=owner).json()["results"]}["shift.open_too_long"]
    assert row["status"] == "pass"
    db = session_factory()
    db.get(Shift, shift["id"]).start_time = datetime.now(timezone.utc) - timedelta(hours=30)
    db.commit(); db.close()
    client.post("/api/checks/run", headers=owner, json={})
    row = {r["key"]: r for r in client.get(f"/api/checks?day={TODAY}", headers=owner).json()["results"]}["shift.open_too_long"]
    assert row["status"] == "fail" and "Morning" in row["sentence"]
