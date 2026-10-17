"""The records the search box can find: only what the signed-in role may open."""

from test_api_terminal_vehicle_dtp import _account, _customer, _terminal  # noqa: F401
from test_api_sales import pump  # noqa: F401  (fixture)


def _kinds(client, h):
    r = client.get("/api/search/records", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_manager_finds_employees_nozzles_tanks_customers_and_vehicles(client, manager, pump):
    c = _customer(client, manager, "Ravi Transport")
    _account(client, manager, c, limit="50000.00")
    assert _terminal(client, manager, pump, customer_id=c["id"]).status_code == 201
    rows = _kinds(client, manager)
    kinds = {r["kind"] for r in rows}
    assert {"Employee", "Nozzle", "Dispenser", "Tank", "Customer", "Vehicle"} <= kinds
    vehicle = next(r for r in rows if r["kind"] == "Vehicle")
    assert vehicle["label"] == "MH12AB1234" and vehicle["hint"] == "Ravi Transport" and vehicle["to"] == f"/credit/customers/{c['id']}"


def test_an_attendant_gets_nothing_they_could_not_open(client, attendant, manager, pump):
    _customer(client, manager, "Secret Customer")
    rows = _kinds(client, attendant)
    assert {r["kind"] for r in rows}.isdisjoint({"Employee", "User", "Customer", "Tank", "Supplier"})
    assert not any("Secret" in r["label"] for r in rows)


def test_user_accounts_are_only_for_those_who_manage_users(client, manager, admin):
    assert not any(r["kind"] == "User" for r in _kinds(client, manager))
    assert any(r["kind"] == "User" for r in _kinds(client, admin))


def test_search_needs_a_session(client):
    assert client.get("/api/search/records", headers={"X-Launch-Secret": client.headers["X-Launch-Secret"]}).status_code == 401
