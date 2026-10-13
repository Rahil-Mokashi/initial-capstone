"""The owner's two-sided daily report. Built in Python (app/services/daily_report_*); printed by the
desktop shell's existing HTML print preview, which also does Print and Save as PDF."""

from datetime import date
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, Out
from api.services import Services
from app.services.daily_report_plus import content_hash
from app.services.daily_report_service import report_to_dict

router = APIRouter(tags=["daily-report"])


class DailyReportOut(Out):
    day: date
    style: str
    html: str
    report: dict[str, Any]
    finalised_at: Optional[str] = None
    finalised_hash: Optional[str] = None
    current_hash: Optional[str] = None


@router.get("/daily-report", response_model=DailyReportOut)
def daily_report(
    day: Optional[date] = None,
    style: Optional[Literal["classic", "plus"]] = None,
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
):
    day = day or date.today()
    report = services.daily_report.build(user.id, day)
    style = style or services.pump_settings.get("daily_report_style")
    company = services.settings.get_company_profile()
    html = services.render_report(report, company, style, user.id)
    final = services.report_finaliser.latest(day)
    return DailyReportOut(
        day=day, style=style, html=html, report=report_to_dict(report),
        finalised_at=final.finalised_at.isoformat() if final else None, finalised_hash=final.content_hash if final else None,
        current_hash=content_hash(report),
    )


class FinaliseIn(In):
    day: date
    style: Literal["classic", "plus"] = "classic"


@router.post("/daily-report/finalise", response_model=DailyReportOut, status_code=201)
def finalise(body: FinaliseIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.report_finaliser.finalise(user.id, body.day, body.style)
    return daily_report(body.day, body.style, user, services)
