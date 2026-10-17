from api_helpers import PASSWORD, SECRET, audit_chain_ok, audit_events, login


def test_login_success_returns_token_user_and_permissions(client, session_factory):
    resp = client.post("/api/auth/login", json={"username": "manager1", "password": PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] and body["expires_at"]
    assert body["user"]["username"] == "manager1"
    assert body["user"]["role"] == "MANAGER"
    assert "inventory.manage" in body["user"]["permissions"]
    assert "password_hash" not in resp.text
    assert len(audit_events(session_factory, "login_success")) == 1
    assert audit_chain_ok(session_factory)


def test_login_wrong_password_is_401_with_generic_message_and_audit(client, session_factory):
    resp = client.post("/api/auth/login", json={"username": "manager1", "password": "nope"})
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert err["code"] == "invalid_credentials"
    assert err["details"]["attempts_remaining"] >= 1
    assert len(audit_events(session_factory, "login_failed")) == 1


def test_unknown_user_gets_the_same_response_shape(client):
    resp = client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_repeated_failures_lock_the_account(client):
    for _ in range(10):
        resp = client.post("/api/auth/login", json={"username": "attendant1", "password": "nope"})
        if resp.json()["error"]["code"] == "account_locked":
            break
    else:  # pragma: no cover
        raise AssertionError("account never locked")
    assert resp.status_code == 401
    assert "locked_until" in resp.json()["error"]["details"]
    # even the right password is refused while locked
    assert client.post("/api/auth/login", json={"username": "attendant1", "password": PASSWORD}).status_code == 401


def test_login_validation_422(client):
    assert client.post("/api/auth/login", json={"username": "", "password": ""}).status_code == 422
    assert client.post("/api/auth/login", json={"username": "x"}).status_code == 422
    resp = client.post("/api/auth/login", json={"username": "x", "password": "y", "extra": 1})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_me_returns_the_signed_in_user(client, manager):
    resp = client.get("/api/auth/me", headers=manager)
    assert resp.status_code == 200 and resp.json()["username"] == "manager1"


def test_logout_ends_the_session(client, manager, session_factory):
    assert client.post("/api/auth/logout", headers=manager).status_code == 204
    assert client.get("/api/auth/me", headers=manager).status_code == 401
    assert len(audit_events(session_factory, "logout")) == 1
    assert audit_chain_ok(session_factory)


def test_forced_password_change_blocks_everything_but_auth_endpoints(client):
    headers = login(client, "newhire1")
    assert client.get("/api/auth/me", headers=headers).json()["must_change_password"] is True
    blocked = client.get("/api/tanks", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"


def test_change_password_success_then_unblocked(client, session_factory):
    headers = login(client, "newhire1")
    resp = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "Br4nd-New-Pass!"},
    )
    assert resp.status_code == 200 and resp.json()["must_change_password"] is False
    assert client.get("/api/tanks", headers=headers).status_code == 200
    assert audit_chain_ok(session_factory)


def test_change_password_wrong_current_and_weak_new(client):
    headers = login(client, "newhire1")
    wrong = client.post("/api/auth/change-password", headers=headers,
                        json={"current_password": "bad", "new_password": "Br4nd-New-Pass!"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "authentication_failed"
    weak = client.post("/api/auth/change-password", headers=headers,
                       json={"current_password": PASSWORD, "new_password": "abc"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"


def test_change_password_validation_422(client, manager):
    assert client.post("/api/auth/change-password", headers=manager, json={}).status_code == 422


# ---- sign-in extras: PIN, lock screen, set PIN, forgot password, device name ------------------------
PIN = "483920"


def _set_pin(client, headers, pin=PIN):
    return client.post("/api/auth/pin", headers=headers, json={"current_password": PASSWORD, "pin": pin})


def test_set_pin_then_sign_in_with_it(client, manager, session_factory):
    me = client.get("/api/auth/me", headers=manager).json()
    assert me["has_pin"] is False
    done = _set_pin(client, manager)
    assert done.status_code == 200 and done.json()["has_pin"] is True
    assert "pin_hash" not in done.text
    ok = client.post("/api/auth/login", json={"username": "manager1", "password": PIN, "use_pin": True})
    assert ok.status_code == 200 and ok.json()["user"]["has_pin"] is True
    # the PIN is not accepted as a password, nor the password as a PIN
    assert client.post("/api/auth/login", json={"username": "manager1", "password": PIN}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "manager1", "password": PASSWORD, "use_pin": True}).status_code == 401
    assert len(audit_events(session_factory, "user_pin_set")) == 1 and audit_chain_ok(session_factory)


def test_pin_rules(client, manager):
    assert _set_pin(client, manager, "12").status_code == 422
    assert _set_pin(client, manager, "abcdef").status_code == 422
    wrong = client.post("/api/auth/pin", headers=manager, json={"current_password": "nope", "pin": PIN})
    assert wrong.status_code == 401
    # an account with no PIN fails exactly like a wrong one (no way to probe who has a PIN)
    a = client.post("/api/auth/login", json={"username": "accountant1", "password": PIN, "use_pin": True})
    b = client.post("/api/auth/login", json={"username": "accountant1", "password": "000000", "use_pin": True})
    assert a.status_code == b.status_code == 401 and a.json()["error"]["message"] == b.json()["error"]["message"]


def test_wrong_pins_lock_the_account_like_wrong_passwords(client, manager):
    _set_pin(client, manager)
    for _ in range(10):
        r = client.post("/api/auth/login", json={"username": "manager1", "password": "000000", "use_pin": True})
        if r.json()["error"]["code"] == "account_locked":
            break
    else:  # pragma: no cover
        raise AssertionError("never locked")
    assert "locked_until" in r.json()["error"]["details"]


def test_login_reports_the_previous_sign_in_for_the_account_menu(client):
    first = client.post("/api/auth/login", json={"username": "manager1", "password": PASSWORD}).json()
    assert first["user"]["last_login"] is None
    second = client.post("/api/auth/login", json={"username": "manager1", "password": PASSWORD}).json()
    assert second["user"]["last_login"]


def test_lock_screen_reauthenticates_without_a_new_session(client, manager, session_factory):
    ok = client.post("/api/auth/reauthenticate", headers=manager, json={"credential": PASSWORD})
    assert ok.status_code == 204
    bad = client.post("/api/auth/reauthenticate", headers=manager, json={"credential": "nope"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"
    assert client.get("/api/auth/me", headers=manager).status_code == 200  # same session still valid
    assert len(audit_events(session_factory, "device_unlocked")) == 1
    _set_pin(client, manager)
    assert client.post("/api/auth/reauthenticate", headers=manager, json={"credential": PIN, "use_pin": True}).status_code == 204
    assert client.post("/api/auth/reauthenticate", headers=manager, json={"credential": PIN}).status_code == 401


def test_forgot_password_with_an_admin_code(client, admin, session_factory):
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["username"] == "attendant1")
    code = client.post(f"/api/users/{uid}/reset-code", headers=admin, json={}).json()["code"]
    # no session needed
    wrong = client.post("/api/auth/forgot-password", json={"username": "attendant1", "code": "00000000", "new_password": "N3w!Passw0rd"})
    assert wrong.status_code == 401
    weak = client.post("/api/auth/forgot-password", json={"username": "attendant1", "code": code, "new_password": "weak"})
    assert weak.status_code == 422
    ok = client.post("/api/auth/forgot-password", json={"username": "attendant1", "code": code, "new_password": "N3w!Passw0rd"})
    assert ok.status_code == 204
    assert client.post("/api/auth/login", json={"username": "attendant1", "password": "N3w!Passw0rd"}).status_code == 200
    # single use
    again = client.post("/api/auth/forgot-password", json={"username": "attendant1", "code": code, "new_password": "An0ther!Passw0rd"})
    assert again.status_code == 401
    ghost = client.post("/api/auth/forgot-password", json={"username": "ghost", "code": code, "new_password": "N3w!Passw0rd"})
    assert ghost.status_code == 401 and ghost.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_device_name_for_the_sign_in_screen(client):
    d = client.get("/api/system/device").json()
    assert isinstance(d["device"], str) and d["device"]
    assert d["mode"] == "single"  # no Main PC settings: this PC works on its own
