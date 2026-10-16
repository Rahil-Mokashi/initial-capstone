import time

from api import check_worker
from test_api_checks import TODAY, _by_key, _close_pump, _shift_checks
from test_api_sales import pump  # noqa: F401  (fixture)


def test_save_returns_before_the_checks_and_the_checks_arrive_after(client, owner, manager, pump, monkeypatch):
    monkeypatch.setattr(check_worker, "INLINE", False)
    monkeypatch.setattr(check_worker, "QUIET_SECONDS", 0.2)
    started = time.perf_counter()
    _close_pump(client, manager, pump)
    assert time.perf_counter() - started < 0.2 + 5  # the reply did not wait for the quiet period plus the run
    assert "shift.litres_match_meters" not in _by_key(_shift_checks(client, owner))  # still queued
    assert check_worker.wait_idle(client.app, timeout=30)
    assert _by_key(_shift_checks(client, owner))["shift.litres_match_meters"]["status"] == "pass"


def test_a_burst_of_saves_runs_the_checks_once(client, owner, monkeypatch):
    monkeypatch.setattr(check_worker, "INLINE", False)
    monkeypatch.setattr(check_worker, "QUIET_SECONDS", 0.3)
    runs = []
    monkeypatch.setattr(check_worker, "run_checks", lambda *a: runs.append(a))
    for n in range(5):
        assert client.post("/api/customers", headers=owner, json={"name": f"Burst {n}"}).status_code in (200, 201)
    assert check_worker.wait_idle(client.app, timeout=10)
    assert len(runs) == 1
