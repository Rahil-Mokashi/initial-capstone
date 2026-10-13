"""Audit log viewer. Same AuditService calls as app/ui/audit_log_window.py."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services, require_permission
from api.schemas import Out
from api.services import Services
from app.core.constants import Permission

router = APIRouter(tags=["audit"])


class AuditEntryOut(Out):
    id: str
    created_at: datetime
    event_type: str
    actor: Optional[str] = None
    # The PC (and, on a Main PC, its address) the action came from.
    device: Optional[str] = None
    entity: str
    description: str


class ActorOut(Out):
    id: str
    username: str


class VerifyOut(Out):
    intact: bool
    problems: list[str]


@router.get("/audit", response_model=list[AuditEntryOut])
def search(
    event_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
):
    entries = services.audit.search(
        user.id, event_type=event_type or None, filter_actor_id=actor_id or None, date_from=date_from, date_to=date_to
    )
    return [
        AuditEntryOut(
            id=e.id,
            created_at=e.created_at,
            event_type=e.event_type,
            actor=e.actor.username if e.actor else None,
            device=e.device_info or None,
            entity=f"{e.entity_type} {e.entity_id}" if e.entity_type else "",
            description=e.description or "",
        )
        for e in entries
    ]


@router.get("/audit/actors", response_model=list[ActorOut])
def actors(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """The All users filter list; the Qt screen reads the same user list."""
    require_permission(services, user.id, Permission.AUDIT_VIEW)
    return [ActorOut(id=u.id, username=u.username) for u in services.user_repo.list_all()]


@router.post("/audit/verify", response_model=VerifyOut)
def verify(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    intact, problems = services.audit.verify_trail(user.id)
    return VerifyOut(intact=intact, problems=problems[:10])
