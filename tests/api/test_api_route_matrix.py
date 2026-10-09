"""Security checks that cover EVERY route automatically, including ones added later.

Walks the real route table: any /api route that is not explicitly public must (a) reject a request with no
launch secret (403), (b) reject a request with the secret but no session token (401), (c) reject a garbage
token (401). A new router cannot forget authentication without this test failing.
"""

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api_helpers import SECRET

PUBLIC_WITH_SECRET_ONLY = {"/api/health", "/api/system/shutdown"}
LOGIN = "/api/auth/login"


def _routes(app):
    """(METHOD, path) for every operation, read from the OpenAPI schema (the router tree is nested)."""
    out = []
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                out.append((method.upper(), path))
    return sorted(out)


@pytest.fixture()
def bare_app(session_factory, users):
    return create_app(SECRET, session_factory=session_factory, session_timeout_hours=8)


def _all(session_factory):
    # Built once at import time would need a DB; the route table does not, so use a stub factory.
    app = create_app(SECRET, session_factory=lambda: None, session_timeout_hours=1)
    return _routes(app)


ROUTES = _all(None)


def _fill(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", "x", path)


def test_route_table_is_not_empty():
    assert len(ROUTES) >= 16


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_route_needs_the_launch_secret(bare_app, method, path):
    client = TestClient(bare_app, base_url="http://127.0.0.1")
    resp = client.request(method, _fill(path), json={})
    assert resp.status_code == 403, (method, path, resp.text)
    wrong = client.request(method, _fill(path), json={}, headers={"X-Launch-Secret": "nope"})
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "launch_secret_invalid"


@pytest.mark.parametrize(
    "method,path", [r for r in ROUTES if r[1] not in PUBLIC_WITH_SECRET_ONLY and r[1] != LOGIN]
)
def test_every_other_route_needs_a_session(bare_app, method, path):
    client = TestClient(bare_app, base_url="http://127.0.0.1", headers={"X-Launch-Secret": SECRET})
    none = client.request(method, _fill(path), json={})
    assert none.status_code == 401, (method, path, none.text)
    garbage = client.request(method, _fill(path), json={}, headers={"Authorization": "Bearer not-real"})
    assert garbage.status_code == 401, (method, path, garbage.text)
