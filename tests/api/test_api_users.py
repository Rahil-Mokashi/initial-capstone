from api_helpers import PASSWORD, audit_chain_ok, audit_events


def _roles(client, h):
    return {r["name"]: r["id"] for r in client.get("/api/users/roles", headers=h).json()}


def _user(client, h, username):
    return next(u for u in client.get("/api/users", headers=h).json() if u["username"] == username)


def test_list_and_roles(client, admin, session_factory):
    rows = client.get("/api/users", headers=admin).json()
    assert {"manager1", "accountant1"} <= {r["username"] for r in rows}
    assert rows[0]["status"] in {"Active", "Inactive", "Locked"} and "password_hash" not in rows[0]
    assert len(_roles(client, admin)) >= 6


def test_create_user_then_sign_in(client, admin, session_factory):
    roles = _roles(client, admin)
    body = {"username": "new.user", "email": "new@example.com", "password": "Str0ngPass!x", "role_id": next(iter(roles.values())), "first_name": "New"}
    resp = client.post("/api/users", headers=admin, json=body)
    assert resp.status_code == 201 and resp.json()["username"] == "new.user" and "password" not in resp.json()
    assert client.post("/api/auth/login", json={"username": "new.user", "password": "Str0ngPass!x"}).status_code == 200
    assert len(audit_events(session_factory, "user_created")) == 1 and audit_chain_ok(session_factory)
    dup = client.post("/api/users", headers=admin, json=body)
    assert dup.status_code in (409, 422)


def test_create_validation(client, admin):
    rid = next(iter(_roles(client, admin).values()))
    for over in ({"username": "a"}, {"email": "nope"}, {"password": "short"}):
        body = {"username": "valid.name", "email": "v@example.com", "password": "Str0ngPass!x", "role_id": rid, **over}
        assert client.post("/api/users", headers=admin, json=body).status_code == 422


def test_deactivate_activate_role_change_and_reset(client, admin, session_factory):
    target = _user(client, admin, "attendant1")
    uid = target["id"]
    assert client.post(f"/api/users/{uid}/active", headers=admin, json={"is_active": False}).json()["status"] == "Inactive"
    assert client.post(f"/api/users/{uid}/active", headers=admin, json={"is_active": True, "reason": "back"}).json()["status"] == "Active"
    roles = _roles(client, admin)
    changed = client.post(f"/api/users/{uid}/role", headers=admin, json={"role_id": roles["ACCOUNTANT"]})
    assert changed.status_code == 200 and changed.json()["role"] == "ACCOUNTANT"
    reset = client.post(f"/api/users/{uid}/reset-password", headers=admin, json={"new_password": "Temp0rary!x9"})
    assert reset.status_code == 200
    assert client.post("/api/auth/login", json={"username": "attendant1", "password": "Temp0rary!x9"}).json()["user"]["must_change_password"] is True
    assert client.post(f"/api/users/{uid}/reset-password", headers=admin, json={"new_password": "weak"}).status_code == 422
    assert audit_chain_ok(session_factory)


def test_unlock_only_when_locked_and_reset_code(client, admin):
    uid = _user(client, admin, "attendant1")["id"]
    assert client.post(f"/api/users/{uid}/unlock", headers=admin, json={}).status_code == 409
    code = client.post(f"/api/users/{uid}/reset-code", headers=admin, json={}).json()["code"]
    assert len(code) >= 6
    done = client.post("/api/auth/login", json={"username": "attendant1", "password": PASSWORD})
    assert done.status_code == 200  # generating a code does not lock or change the password


def test_only_user_managers(client, manager, accountant, attendant):
    for h in (manager, accountant, attendant):
        assert client.get("/api/users", headers=h).status_code == 403
        assert client.get("/api/users/roles", headers=h).status_code == 403
        assert client.post("/api/users/x/unlock", headers=h, json={}).status_code == 403


def test_unknown_user_is_404(client, admin):
    assert client.post("/api/users/nope/active", headers=admin, json={"is_active": False}).status_code == 404
