"""The Checks screen: today's verifications, failures first, history per day, explanations.

Thin: results come from CheckService, which stores them append-only. Nothing here can change a
status. `POST /checks/run` recomputes a day from the data (same code that runs after every save).
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Request

from api.check_worker import is_updating
from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, Out, Reason
from api.services import Services
from app.core.constants import Permission
from app.services.check_runners import ExistingDataChecks  # noqa: F401  (documented dependency)

router = APIRouter(tags=["checks"])

_SCALE = {"rs": "0.01", "litres": "0.001", "count": "1"}


def _num(unit: str, value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return str(Decimal(value).quantize(Decimal(_SCALE.get(unit, "0.01"))))


class ExplanationOut(Out):
    text: str
    by: str
    at: datetime


class CheckOut(Out):
    id: str
    key: str
    scope_type: str
    scope_id: str
    business_date: date
    area: str
    sentence: str
    expected: Optional[str]
    actual: Optional[str]
    difference: Optional[str]
    unit: str
    status: str
    links: list[dict]
    run_at: datetime
    explanations: list[ExplanationOut]


class ChecksSummaryOut(Out):
    total: int
    passed: int
    warned: int
    failed: int


class DayChecksOut(Out):
    day: date
    summary: ChecksSummaryOut
    results: list[CheckOut]


def _row(r) -> CheckOut:
    return CheckOut(
        id=r.id, key=r.check_key, scope_type=r.scope_type, scope_id=r.scope_id, business_date=r.business_date,
        area=r.area, sentence=r.sentence, expected=_num(r.unit, r.expected), actual=_num(r.unit, r.actual),
        difference=_num(r.unit, r.difference), unit=r.unit, status=r.status, links=json.loads(r.links or "[]"),
        run_at=r.run_at,
        explanations=[
            ExplanationOut(text=e.text, by=(e.created_by.username if e.created_by else ""), at=e.created_at)
            for e in r.explanations
        ],
    )


class ChecksStatusOut(Out):
    updating: bool


@router.get("/checks/status", response_model=ChecksStatusOut)
def checks_status(request: Request, user: CurrentUser = Depends(current_user)):
    """True while the background worker still has checks to run after a save (screens say "checks updating")."""
    return ChecksStatusOut(updating=is_updating(request.app))


@router.get("/checks", response_model=DayChecksOut)
def checks_for_day(
    day: Optional[date] = None, area: Optional[str] = None,
    user: CurrentUser = Depends(current_user), services: Services = Depends(get_services),
):
    day = day or date.today()
    rows = services.checks.results_for_day(user.id, day, area)
    return DayChecksOut(day=day, summary=ChecksSummaryOut(**services.checks.summary(rows)), results=[_row(r) for r in rows])


@router.get("/checks/history", response_model=list[CheckOut])
def checks_history(day: date, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [_row(r) for r in services.checks.history_for_day(user.id, day)]


@router.get("/checks/days", response_model=list[date])
def checks_days(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.checks.recent_days(user.id)


class RunIn(In):
    day: Optional[date] = None


@router.post("/checks/run", response_model=DayChecksOut)
def run_checks(body: RunIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    from api.deps import require_permission

    require_permission(services, user.id, Permission.CHECK_VIEW)
    day = body.day or date.today()
    services.run_all_checks(user.id, day)
    rows = services.checks.results_for_day(user.id, day)
    return DayChecksOut(day=day, summary=ChecksSummaryOut(**services.checks.summary(rows)), results=[_row(r) for r in rows])


class ExplainIn(In):
    text: Reason


@router.post("/checks/{result_id}/explanations", response_model=CheckOut, status_code=201)
def explain(result_id: str, body: ExplainIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.checks.explain(user.id, result_id, body.text)
    return _row(services.checks.get_result(user.id, result_id))
