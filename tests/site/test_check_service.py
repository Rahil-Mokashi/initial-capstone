from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import PermissionDeniedError
from app.services.check_service import CheckSpec, evaluate

D = Decimal
DAY = date(2026, 10, 12)


def spec(expected="100.00", actual="100.00", **kw):
    base = dict(key="shift.tenders_add_up", scope_type="shift", scope_id="s1", business_date=DAY, area="Daily report",
                sentence="Shift 1: payment modes add up to the shift total",
                expected=None if expected is None else D(expected), actual=None if actual is None else D(actual))
    base.update(kw)
    return CheckSpec(**base)


def test_evaluate_exact_match_passes():
    assert evaluate(spec()) == "pass"


def test_evaluate_any_difference_fails_by_default():
    assert evaluate(spec(actual="100.01")) == "fail"


def test_evaluate_warn_band_and_pass_band():
    assert evaluate(spec(actual="100.50", warn_within=D("1"))) == "warn"
    assert evaluate(spec(actual="100.50", warn_within=D("1"), pass_within=D("0.5"))) == "pass"
    assert evaluate(spec(actual="102", warn_within=D("1"))) == "fail"


def test_evaluate_missing_side_is_a_failure_not_a_pass():
    assert evaluate(spec(actual=None)) == "fail"
    assert evaluate(spec(expected=None)) == "fail"


def test_record_stores_difference_and_audits(svc, uid):
    r = svc.checks.record(uid["OWNER"], spec(actual="90.00"))
    assert (r.status, r.difference) == ("fail", D("-10.000"))
    events = [e for e in svc.audit_repo.search(event_type="check_recorded")]
    assert len(events) == 1 and "FAIL" in events[0].description


def test_same_outcome_is_not_stored_twice_but_a_change_supersedes(svc, uid):
    a = svc.checks.record(uid["OWNER"], spec(actual="90.00"))
    again = svc.checks.record(uid["OWNER"], spec(actual="90.00"))
    assert again.id == a.id
    fixed = svc.checks.record(uid["OWNER"], spec(actual="100.00"))
    assert fixed.id != a.id and fixed.status == "pass"
    current = svc.checks.results_for_day(uid["OWNER"], DAY)
    assert [r.id for r in current] == [fixed.id]
    history = svc.checks.history_for_day(uid["OWNER"], DAY)
    assert {r.id for r in history} == {a.id, fixed.id}  # the earlier failure is never erased


def test_failures_sort_first(svc, uid):
    svc.checks.record(uid["OWNER"], spec(key="a.ok"))
    svc.checks.record(uid["OWNER"], spec(key="b.bad", actual="1"))
    svc.checks.record(uid["OWNER"], spec(key="c.warn", actual="100.5", warn_within=D("1")))
    assert [r.status for r in svc.checks.results_for_day(uid["OWNER"], DAY)] == ["fail", "warn", "pass"]


def test_explanation_records_who_and_never_changes_status(svc, uid):
    r = svc.checks.record(uid["OWNER"], spec(actual="90.00"))
    note = svc.checks.explain(uid["ACCOUNTANT"], r.id, "Cash short, recovered next day")
    assert note.created_by_id == uid["ACCOUNTANT"] and note.created_at is not None
    current = svc.checks.results_for_day(uid["OWNER"], DAY)[0]
    assert current.status == "fail" and [e.text for e in current.explanations] == ["Cash short, recovered next day"]
    assert svc.audit_repo.search(event_type="check_explained")


def test_explanation_needs_text_and_permission(svc, uid):
    r = svc.checks.record(uid["OWNER"], spec(actual="90.00"))
    with pytest.raises(ValueError):
        svc.checks.explain(uid["OWNER"], r.id, "   ")
    with pytest.raises(PermissionDeniedError):
        svc.checks.explain(uid["ATTENDANT"], r.id, "hello")
    with pytest.raises(PermissionDeniedError):
        svc.checks.results_for_day(uid["DATA_ENTRY"], DAY)


def test_unknown_scope_is_refused(svc, uid):
    with pytest.raises(ValueError):
        svc.checks.record(uid["OWNER"], spec(scope_type="galaxy"))


def test_summary_counts():
    class R:  # noqa: D401
        def __init__(self, s):
            self.status = s

    from app.services.check_service import CheckService

    assert CheckService.summary([R("pass"), R("pass"), R("fail"), R("warn")]) == {"total": 4, "passed": 2, "warned": 1, "failed": 1}
