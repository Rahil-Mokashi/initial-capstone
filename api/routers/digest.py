"""The owner's daily digest and the per-owner "reviewed" mark. Thin: DigestService composes the figures from the services that own them."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyOut, Out, VolumeOut
from api.services import Services

router = APIRouter(tags=["digest"])


class DigestShiftOut(Out):
    shift_id: str
    label: str
    total_sale: MoneyOut
    collected: MoneyOut
    difference: MoneyOut
    status: str
    entry_status: Optional[str] = None


class DigestCheckOut(Out):
    sentence: str
    status: str


class DigestReviewedOut(Out):
    by: str
    at: datetime


class DigestOut(Out):
    day: date
    shifts: list[DigestShiftOut]
    total_sale: MoneyOut
    litres_sold: VolumeOut
    credit_sales: MoneyOut
    credit_outstanding: MoneyOut
    checks_total: int
    checks_passed: int
    checks_to_look_at: list[DigestCheckOut]
    waiting: dict[str, int]
    pending_expenses: int
    reviewed: list[DigestReviewedOut]
    reviewed_by_me: bool


class DigestReviewIn(In):
    day: date


def _out(d) -> DigestOut:
    return DigestOut(
        day=d.day, shifts=[DigestShiftOut.model_validate(s, from_attributes=True) for s in d.shifts], total_sale=d.total_sale,
        litres_sold=d.litres_sold, credit_sales=d.credit_sales, credit_outstanding=d.credit_outstanding,
        checks_total=d.checks_total, checks_passed=d.checks_passed,
        checks_to_look_at=[DigestCheckOut(sentence=c.sentence, status=c.status) for c in d.checks_to_look_at],
        waiting=d.waiting, pending_expenses=d.pending_expenses,
        reviewed=[DigestReviewedOut(by=name, at=at) for name, at in d.reviewed], reviewed_by_me=d.reviewed_by_me,
    )


@router.get("/digest", response_model=DigestOut)
def digest(day: Optional[date] = None, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _out(services.digest.build(user.id, day or services.digest.default_day(user.id)))


@router.post("/digest/review", response_model=DigestOut)
def review(body: DigestReviewIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _out(services.digest.mark_reviewed(user.id, body.day))
