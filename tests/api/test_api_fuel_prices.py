from api_helpers import audit_chain_ok, audit_events


def _fuels(client, headers):
    return client.get("/api/fuel-prices", headers=headers).json()


def test_list_marks_unpriced_fuels(client, manager):
    rows = _fuels(client, manager)
    assert rows and all(r["priced"] is False for r in rows)  # seeded at 0.00
    assert rows[0]["rate_per_liter"] == "0.00"


def test_set_rate_updates_history_and_audits(client, manager, session_factory):
    fuel = _fuels(client, manager)[0]
    resp = client.post(
        f"/api/fuel-prices/{fuel['id']}/rate", headers=manager, json={"new_rate_per_liter": "104.50", "reason": "OMC revision"}
    )
    assert resp.status_code == 200 and resp.json()["rate_per_liter"] == "104.50" and resp.json()["priced"] is True
    hist = client.get(f"/api/fuel-prices/{fuel['id']}/history", headers=manager).json()
    assert [(h["old_rate_per_liter"], h["new_rate_per_liter"], h["reason"]) for h in hist] == [(None, "104.50", "OMC revision")]
    assert len(audit_events(session_factory, "fuel_price_changed")) == 1 and audit_chain_ok(session_factory)


def test_same_price_is_a_conflict_and_extra_places_are_refused(client, manager):
    fid = _fuels(client, manager)[0]["id"]
    ok = {"new_rate_per_liter": "100.00", "reason": "x"}
    assert client.post(f"/api/fuel-prices/{fid}/rate", headers=manager, json=ok).status_code == 200
    assert client.post(f"/api/fuel-prices/{fid}/rate", headers=manager, json=ok).status_code == 409
    bad = {"new_rate_per_liter": "100.005", "reason": "x"}
    assert client.post(f"/api/fuel-prices/{fid}/rate", headers=manager, json=bad).status_code == 422
    num = {"new_rate_per_liter": 100.5, "reason": "x"}
    assert client.post(f"/api/fuel-prices/{fid}/rate", headers=manager, json=num).status_code == 422


def test_nonpositive_rate_rejected(client, manager):
    fid = _fuels(client, manager)[0]["id"]
    for body in ({"new_rate_per_liter": "0", "reason": "x"}, {"new_rate_per_liter": "10001", "reason": "x"}):
        assert client.post(f"/api/fuel-prices/{fid}/rate", headers=manager, json=body).status_code == 422


def test_permissions(client, accountant, manager, session_factory):
    fid = _fuels(client, manager)[0]["id"]
    assert client.get("/api/fuel-prices", headers=accountant).status_code == 200
    body = {"new_rate_per_liter": "100", "reason": "x"}
    assert client.post(f"/api/fuel-prices/{fid}/rate", headers=accountant, json=body).status_code == 403
    assert audit_events(session_factory, "fuel_price_changed") == []


def test_unknown_fuel_is_404(client, manager):
    assert client.get("/api/fuel-prices/nope/history", headers=manager).status_code == 404


def test_reason_is_optional_and_recorded_as_such(client, manager):
    fid = _fuels(client, manager)[0]["id"]
    assert client.post(f"/api/fuel-prices/{fid}/rate", headers=manager, json={"new_rate_per_liter": "99"}).status_code == 200
    hist = client.get(f"/api/fuel-prices/{fid}/history", headers=manager).json()
    assert hist[0]["reason"] == "No reason given"
