from api_helpers import audit_chain_ok, audit_events


def _supplier(client, h, name="Indian Oil"):
    r = client.post("/api/suppliers", headers=h, json={"name": name, "phone": "9999999999"})
    assert r.status_code == 201, r.text
    return r.json()


def _order(client, h, supplier, fuel_id, qty="5000.000", rate="90.50"):
    r = client.post(
        "/api/purchase-orders",
        headers=h,
        json={
            "supplier_id": supplier["id"],
            "expected_delivery_date": "2026-11-01",
            "items": [{"fuel_id": fuel_id, "quantity_ordered": qty, "rate_per_liter": rate}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_supplier_create_status_and_permissions(client, manager, accountant, attendant, session_factory):
    s = _supplier(client, manager)
    assert s["status"] == "active"
    assert client.post("/api/suppliers", headers=manager, json={"name": "  "}).status_code == 422
    off = client.post(f"/api/suppliers/{s['id']}/status", headers=manager, json={"status": "inactive", "reason": "x"})
    assert off.json()["status"] == "inactive"
    assert client.post("/api/suppliers", headers=attendant, json={"name": "Z"}).status_code == 403
    assert client.post("/api/suppliers", headers=accountant, json={"name": "Z"}).status_code == 403
    assert audit_chain_ok(session_factory)


def test_order_options_only_active_suppliers(client, manager, fuel_id):
    _supplier(client, manager, "A")
    b = _supplier(client, manager, "B")
    client.post(f"/api/suppliers/{b['id']}/status", headers=manager, json={"status": "inactive"})
    opts = client.get("/api/procurement/order-options", headers=manager).json()
    assert [s["label"] for s in opts["suppliers"]] == ["A"] and opts["fuels"]


def test_order_validation_and_cancel(client, manager, fuel_id):
    s = _supplier(client, manager)
    bad = client.post("/api/purchase-orders", headers=manager, json={"supplier_id": s["id"], "items": []})
    assert bad.status_code == 422
    item = {"fuel_id": fuel_id, "quantity_ordered": "0", "rate_per_liter": "90"}
    assert client.post("/api/purchase-orders", headers=manager, json={"supplier_id": s["id"], "items": [item]}).status_code == 422
    item = {"fuel_id": fuel_id, "quantity_ordered": 10.5, "rate_per_liter": "90"}
    assert client.post("/api/purchase-orders", headers=manager, json={"supplier_id": s["id"], "items": [item]}).status_code == 422
    po = _order(client, manager, s, fuel_id)
    assert po["status"] == "placed" and po["total_quantity"] == "5000.000" and po["items"][0]["rate_per_liter"] == "90.50"
    c = client.post(f"/api/purchase-orders/{po['id']}/cancel", headers=manager, json={})
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert client.post(f"/api/purchase-orders/{po['id']}/cancel", headers=manager, json={}).status_code in (409, 422)
    assert client.get("/api/purchase-orders/nope", headers=manager).status_code == 404


def test_full_delivery_workflow_moves_tank_stock(client, manager, fuel_id, tank, employee_id, session_factory):
    s = _supplier(client, manager)
    po = _order(client, manager, s, fuel_id, qty="1000.000")
    opts = client.get("/api/procurement/arrival-options", headers=manager).json()
    assert opts["tanks"][0]["label"].startswith("T1") and opts["employees"][0]["label"].startswith("EMP-0001")
    arr = client.post(
        f"/api/purchase-orders/{po['id']}/deliveries",
        headers=manager,
        json={"tank_id": tank["id"], "received_by_employee_id": employee_id, "tanker_number": "MH12-1234", "driver_name": "Sam"},
    )
    assert arr.status_code == 201 and arr.json()["status"] == "arrived"
    d = arr.json()["id"]
    # out of order is refused
    assert client.post(f"/api/deliveries/{d}/pre-dip", headers=manager, json={"dip_value": "2500.500"}).status_code == 409
    assert client.post(f"/api/deliveries/{d}/verify-documents", headers=manager).json()["status"] == "documents_verified"
    q = client.post(f"/api/deliveries/{d}/verify-quality", headers=manager, json={"notes": "clean"})
    assert q.json()["status"] == "quality_verified"
    pre = client.post(f"/api/deliveries/{d}/pre-dip", headers=manager, json={"dip_value": "2500.500"})
    assert pre.json()["pre_dip_value"] == "2500.500"
    assert client.post(f"/api/deliveries/{d}/post-dip", headers=manager, json={"dip_value": "2000"}).status_code == 422
    done = client.post(f"/api/deliveries/{d}/post-dip", headers=manager, json={"dip_value": "3500.500"})
    assert done.status_code == 200 and done.json()["status"] == "unloaded" and done.json()["quantity_received"] == "1000.000"
    assert client.get(f"/api/tanks/{tank['id']}", headers=manager).json()["current_stock"] == "3500.500"
    assert client.get(f"/api/purchase-orders/{po['id']}", headers=manager).json()["status"] == "delivered"
    assert client.get(f"/api/deliveries/{d}", headers=manager).json()["status"] == "unloaded"
    assert len(client.get(f"/api/purchase-orders/{po['id']}/deliveries", headers=manager).json()) == 1
    for ev in ("fuel_delivery_arrived", "fuel_delivery_unloaded"):
        assert len(audit_events(session_factory, ev)) == 1
    assert audit_chain_ok(session_factory)


def test_reject_delivery_and_arrival_validation(client, manager, fuel_id, tank, employee_id):
    s = _supplier(client, manager)
    po = _order(client, manager, s, fuel_id)
    url = f"/api/purchase-orders/{po['id']}/deliveries"
    arr = client.post(url, headers=manager, json={"tank_id": tank["id"], "received_by_employee_id": employee_id, "tanker_number": "T-1"}).json()
    rej = client.post(f"/api/deliveries/{arr['id']}/reject", headers=manager, json={"reason": "water in fuel"})
    assert rej.json()["status"] == "rejected" and rej.json()["rejection_reason"] == "water in fuel"
    assert client.post(url, headers=manager, json={"tank_id": tank["id"], "received_by_employee_id": "nope", "tanker_number": "T-2"}).status_code == 404
    assert client.post(url, headers=manager, json={"tank_id": tank["id"], "received_by_employee_id": employee_id, "tanker_number": " "}).status_code == 422


def test_invoices_and_payments(client, manager, accountant, fuel_id, session_factory):
    s = _supplier(client, manager)
    po = _order(client, manager, s, fuel_id)
    inv = client.post(
        "/api/invoices",
        headers=manager,
        json={"invoice_number": "INV-1", "supplier_id": s["id"], "purchase_order_id": po["id"], "invoice_date": "2026-10-10", "due_date": "2026-11-10", "amount": "1000.00"},
    )
    assert inv.status_code == 201 and inv.json()["amount"] == "1000.00" and inv.json()["supplier"] == "Indian Oil"
    iid = inv.json()["id"]
    too_precise = {"invoice_number": "INV-2", "supplier_id": s["id"], "invoice_date": "2026-10-10", "amount": "10.005"}
    assert client.post("/api/invoices", headers=manager, json=too_precise).status_code == 422
    pay = {"payment_date": "2026-10-11", "payment_method": "UPI"}
    assert client.post(f"/api/invoices/{iid}/payments", headers=manager, json={"amount": "400.00", "reference": "r1", **pay}).status_code == 201
    assert client.get(f"/api/invoices/{iid}", headers=manager).json()["status"] == "partially_paid"
    assert client.post(f"/api/invoices/{iid}/payments", headers=manager, json={"amount": "600.00", **pay}).status_code == 201
    assert client.get(f"/api/invoices/{iid}", headers=manager).json()["status"] == "paid"
    assert client.post(f"/api/invoices/{iid}/payments", headers=manager, json={"amount": "1.00", **pay}).status_code in (409, 422)
    amounts = sorted(p["amount"] for p in client.get(f"/api/invoices/{iid}/payments", headers=accountant).json())
    assert amounts == ["400.00", "600.00"]
    assert client.post(f"/api/invoices/{iid}/payments", headers=accountant, json={"amount": "1", **pay}).status_code == 403
    assert client.get("/api/invoices/nope", headers=manager).status_code == 404
    assert audit_chain_ok(session_factory)
