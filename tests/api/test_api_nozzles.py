from api_helpers import audit_chain_ok, audit_events


def _setup(client, h, fuel_id, tank=None):
    d = client.post("/api/dispensers", headers=h, json={"code": "D1"})
    assert d.status_code == 201
    return d.json()


def test_dispenser_lifecycle(client, admin, manager, accountant, session_factory):
    d = _setup(client, manager, None)
    assert d["status"] == "active"
    assert client.post("/api/dispensers", headers=manager, json={"code": "D1"}).status_code == 409
    assert client.post("/api/dispensers", headers=manager, json={"code": "  "}).status_code == 422
    off = client.post(f"/api/dispensers/{d['id']}/status", headers=manager, json={"status": "inactive"})
    assert off.status_code == 200 and off.json()["status"] == "inactive"
    assert [x["code"] for x in client.get("/api/dispensers", headers=accountant).json()] == ["D1"]
    assert client.post("/api/dispensers", headers=accountant, json={"code": "D2"}).status_code == 403
    assert len(audit_events(session_factory, "dispenser_status_changed")) == 1 and audit_chain_ok(session_factory)


def test_nozzle_create_status_and_options(client, manager, accountant, fuel_id, tank, session_factory):
    d = _setup(client, manager, fuel_id)
    options = client.get("/api/nozzles/options", headers=manager).json()
    assert [x["code"] for x in options["dispensers"]] == ["D1"] and options["fuels"] and options["tanks"][0]["label"].startswith("T1")
    body = {"code": "N1", "dispenser_id": d["id"], "fuel_id": fuel_id, "tank_id": tank["id"]}
    n = client.post("/api/nozzles", headers=manager, json=body)
    assert n.status_code == 201 and n.json()["dispenser"] == "D1" and n.json()["status"] == "active"
    assert client.post("/api/nozzles", headers=manager, json=body).status_code in (409, 422)
    m = client.post(f"/api/nozzles/{n.json()['id']}/status", headers=manager, json={"status": "maintenance", "reason": "hose"})
    assert m.json()["status"] == "maintenance"
    assert client.post(f"/api/nozzles/{n.json()['id']}/status", headers=manager, json={"status": "broken"}).status_code == 422
    assert len(client.get("/api/nozzles", headers=accountant).json()) == 1
    assert client.get("/api/nozzles/options", headers=accountant).status_code == 403
    assert client.post("/api/nozzles", headers=accountant, json=body).status_code == 403
    assert audit_chain_ok(session_factory)


def test_unknown_ids_are_404(client, manager):
    assert client.post("/api/nozzles/nope/status", headers=manager, json={"status": "active"}).status_code == 404
    assert client.post("/api/dispensers/nope/status", headers=manager, json={"status": "active"}).status_code == 404


def test_four_nozzles_on_a_dispenser_by_default_and_the_owner_can_change_the_limit(client, manager, owner, fuel_id, tank):
    d = _setup(client, manager, fuel_id)

    def add(n):
        return client.post("/api/nozzles", headers=manager, json={"code": f"N{n}", "dispenser_id": d["id"], "fuel_id": fuel_id, "tank_id": tank["id"]})

    assert [add(n).status_code for n in (1, 2, 3, 4)] == [201] * 4
    assert add(5).status_code == 409  # the default limit is 4
    assert client.put("/api/pump-settings/max_nozzles_per_dispenser", headers=owner, json={"value": "5"}).status_code == 200
    assert add(5).status_code == 201
    assert client.put("/api/pump-settings/max_nozzles_per_dispenser", headers=owner, json={"value": "2.5"}).status_code == 422
