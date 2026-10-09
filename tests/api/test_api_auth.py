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
