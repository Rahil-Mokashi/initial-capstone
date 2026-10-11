"""Protocol-level guarantees: launch secret, bearer token, host binding,
headers, the matrix of 'every endpoint rejects the unauthenticated'."""

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.main import build_server, validate_bind

# (method, path, json body) for every endpoint that needs a signed-in user.
TOKEN_ENDPOINTS = [
    ("GET", "/api/auth/me", None),
    ("POST", "/api/auth/logout", None),
    ("POST", "/api/auth/change-password", {"current_password": "a", "new_password": "b"}),
    ("GET", "/api/lookups/fuels", None),
    ("GET", "/api/lookups/employees", None),
    ("GET", "/api/tanks", None),
    ("GET", "/api/tanks/recent-transactions", None),
    ("POST", "/api/tanks", {"code": "X", "fuel_id": "f", "capacity": "1"}),
    ("GET", "/api/tanks/abc", None),
    ("POST", "/api/tanks/abc/status", {"status": "active", "reason": "r"}),
    ("GET", "/api/tanks/abc/transactions", None),
    ("POST", "/api/tanks/abc/transactions", {"transaction_type": "receipt", "quantity": "1"}),
    ("GET", "/api/tanks/abc/readings", None),
    ("POST", "/api/tanks/abc/readings", {"employee_id": "e", "physical_stock": "1"}),
    ("GET", "/api/tanks/abc/reconciliations", None),
    ("POST", "/api/tanks/abc/reconciliations", {"reconciliation_date": "2026-10-09", "physical_stock": "1"}),
]
SECRET_ONLY_ENDPOINTS = [("GET", "/api/health", None), ("GET", "/api/system/device", None), ("POST", "/api/system/shutdown", None)]
LOGIN = ("POST", "/api/auth/login", {"username": "manager1", "password": "x"})


@pytest.mark.parametrize("method,path,body", TOKEN_ENDPOINTS)
def test_no_token_is_401(client, method, path, body):
    resp = client.request(method, path, json=body)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize("method,path,body", TOKEN_ENDPOINTS)
def test_garbage_token_is_401(client, method, path, body):
    resp = client.request(method, path, json=body, headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "session_expired"


@pytest.mark.parametrize("method,path,body", TOKEN_ENDPOINTS + SECRET_ONLY_ENDPOINTS + [LOGIN])
def test_missing_or_wrong_secret_is_403_even_with_a_valid_token(client, manager, method, path, body):
    token_only = {"Authorization": manager["Authorization"]}
    for headers in (token_only, {**token_only, "X-Launch-Secret": "wrong"}):
        # TestClient merges its default headers; override the secret explicitly.
        c = TestClient(client.app, base_url="http://127.0.0.1")
        resp = c.request(method, path, json=body, headers=headers)
        assert resp.status_code == 403, (path, resp.text)
        assert resp.json()["error"]["code"] == "launch_secret_invalid"


def test_secret_checked_before_token(client):
    c = TestClient(client.app, base_url="http://127.0.0.1")
    resp = c.get("/api/tanks")  # neither
    assert resp.status_code == 403


def test_health_and_shutdown_need_only_the_secret(session_factory, users, secret):
    called = []
    app = create_app(secret, session_factory=session_factory, session_timeout_hours=8,
                     shutdown_callback=lambda: called.append(True))
    c = TestClient(app, base_url="http://127.0.0.1", headers={"X-Launch-Secret": secret})
    assert c.get("/api/health").json() == {"status": "ok"}
    assert c.post("/api/system/shutdown").status_code == 202
    assert called == [True]


def test_unknown_host_header_is_rejected(session_factory, users, secret):
    app = create_app(secret, session_factory=session_factory, session_timeout_hours=8)
    c = TestClient(app, base_url="http://evil.example.com", headers={"X-Launch-Secret": secret})
    assert c.get("/api/health").status_code == 400


def test_responses_carry_a_strict_csp_and_no_cors(client):
    resp = client.get("/api/health", headers={"Origin": "http://evil.example.com"})
    csp = resp.headers["content-security-policy"]
    assert csp.startswith("default-src 'self'")
    assert "unsafe-eval" not in csp and "*" not in csp
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}


def test_docs_and_openapi_are_not_served(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_server_refuses_to_bind_anything_but_loopback(session_factory):
    assert validate_bind("127.0.0.1") == "127.0.0.1"
    for host in ("0.0.0.0", "::", "localhost", "192.168.1.5", ""):
        with pytest.raises(ValueError):
            validate_bind(host)
        with pytest.raises(ValueError):
            build_server(host, 8123, "s", None, session_factory=session_factory, session_timeout_hours=8)


def test_built_server_listens_on_loopback_only(session_factory):
    server = build_server("127.0.0.1", 8123, "s", None, session_factory=session_factory, session_timeout_hours=8)
    assert server.config.host == "127.0.0.1"


def test_static_ui_is_served_without_credentials_but_api_is_not(session_factory, users, tmp_path, secret):
    (tmp_path / "index.html").write_text("<html>hi</html>")
    app = create_app(secret, session_factory=session_factory, session_timeout_hours=8, web_dir=tmp_path)
    c = TestClient(app, base_url="http://127.0.0.1")
    assert c.get("/").status_code == 200
    assert c.get("/api/tanks").status_code == 403
