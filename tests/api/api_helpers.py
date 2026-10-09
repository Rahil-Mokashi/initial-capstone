"""Shared constants/helpers for the API tests (importable: tests/api is on sys.path)."""

from fastapi.testclient import TestClient

from app.repositories.audit_log_repository import AuditLogRepository

SECRET = "test-launch-secret"
PASSWORD = "Passw0rd!x"


def login(client: TestClient, username: str) -> dict:
    """Headers (secret + bearer) for a signed-in user."""
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}", "X-Launch-Secret": SECRET}


def audit_chain_ok(session_factory) -> bool:
    session = session_factory()
    try:
        ok, problems = AuditLogRepository(session).verify_chain()
        assert ok, problems
        return ok
    finally:
        session.close()


def audit_events(session_factory, event_type: str) -> list:
    from app.models.audit_log import AuditLog

    session = session_factory()
    try:
        return session.query(AuditLog).filter_by(event_type=event_type).all()
    finally:
        session.close()
