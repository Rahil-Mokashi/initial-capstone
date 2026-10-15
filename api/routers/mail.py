"""The owner's email summary screen: status, outbox, a test message, and the mail password (write-only).

Thin: MailService owns the rules. The password goes to the DPAPI-protected secret file and is never returned.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request

from api.deps import CurrentUser, current_user, get_services, require_permission
from api.errors import ApiError
from api.schemas import In, Out
from api.services import Services
from app.core.constants import Permission
from app.services.mail_service import MailNotReady

router = APIRouter(prefix="/mail", tags=["mail"])


class MailOutboxOut(Out):
    day: str
    subject: str
    status: str
    attempts: int
    last_error: Optional[str] = None
    sent_at: Optional[datetime] = None


class MailStatusOut(Out):
    enabled: bool
    problems: list[str]
    password_set: bool
    pending: int
    last_sent: Optional[datetime] = None
    outbox: list[MailOutboxOut]


class MailPasswordIn(In):
    password: str


class MailTestOut(Out):
    message: str


def _status(services: Services, user: CurrentUser) -> MailStatusOut:
    s = services.mail.status(user.id)
    return MailStatusOut(
        enabled=s["enabled"], problems=s["problems"], password_set=s["password_set"], pending=s["pending"], last_sent=s["last_sent"],
        outbox=[MailOutboxOut(day=r.day.isoformat(), subject=r.subject, status=r.status, attempts=r.attempts, last_error=r.last_error, sent_at=r.sent_at) for r in s["outbox"]],
    )


@router.get("", response_model=MailStatusOut)
def status(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _status(services, user)


@router.post("/test", response_model=MailTestOut)
def send_test(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    try:
        return MailTestOut(message=services.mail.send_test(user.id))
    except MailNotReady as exc:
        raise ApiError(422, "mail_not_ready", str(exc))


@router.put("/password", status_code=204)
def set_password(body: MailPasswordIn, request: Request, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    require_permission(services, user.id, Permission.MAIL_MANAGE)
    from api.lan.config import LanConfigError

    try:
        services.secrets.set("mail", body.password)
    except LanConfigError as exc:
        raise ApiError(422, "cannot_protect_password", str(exc))
    services.audit_repo.record("mail_password_set", actor_id=user.id, description="The mail password was changed")
