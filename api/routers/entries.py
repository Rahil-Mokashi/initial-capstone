"""Review of shift entries: Entered -> Verified -> Approved -> Locked, and the owner's reopen with a reason.

Thin: EntryWorkflowService owns every rule (and writes the audit log). The lock itself is enforced for every write in
app/services/entry_lock_guard.py, not here.
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, Out
from api.services import Services

router = APIRouter(tags=["entries"])


class EntryEventOut(Out):
    action: str
    from_status: Optional[str] = None
    to_status: str
    by: Optional[str] = None
    at: datetime
    reason: Optional[str] = None


class EntryOut(Out):
    shift_id: str
    shift_date: date
    shift_label: str
    status: str
    events: list[EntryEventOut]


class EntryReopenIn(In):
    reason: str = ""


def _out(view) -> EntryOut:
    return EntryOut(
        shift_id=view.shift_id, shift_date=view.shift_date, shift_label=view.shift_label, status=view.status,
        events=[
            EntryEventOut(action=e.action, from_status=e.from_status, to_status=e.to_status, at=e.at, reason=e.reason,
                          by=(e.by.username if e.by else None))
            for e in view.events
        ],
    )


def _one(services: Services, user: CurrentUser, shift_id: str) -> EntryOut:
    entry = services.entries.entry_for(shift_id)
    shift = services.shift_repo.get_by_id(shift_id)
    from app.services.entry_workflow_service import EntryView

    return _out(EntryView(shift_id, shift.shift_date, shift.shift_label, entry.status, list(entry.events)))


@router.get("/entries", response_model=list[EntryOut])
def list_entries(date_from: Optional[date] = None, date_to: Optional[date] = None, user: CurrentUser = Depends(current_user),
                 services: Services = Depends(get_services)):
    today = date.today()
    from datetime import timedelta

    return [_out(v) for v in services.entries.list_between(user.id, date_from or today - timedelta(days=14), date_to or today)]


@router.post("/entries/{shift_id}/verify", response_model=EntryOut)
def verify(shift_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.entries.verify(user.id, shift_id)
    return _one(services, user, shift_id)


@router.post("/entries/{shift_id}/approve", response_model=EntryOut)
def approve(shift_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.entries.approve(user.id, shift_id)
    return _one(services, user, shift_id)


class EntryLockIn(In):
    override_reason: str = ""


@router.post("/entries/{shift_id}/lock", response_model=EntryOut)
def lock(shift_id: str, body: EntryLockIn = EntryLockIn(), user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.entries.lock(user.id, shift_id, body.override_reason)
    return _one(services, user, shift_id)


@router.post("/entries/{shift_id}/reopen", response_model=EntryOut)
def reopen(shift_id: str, body: EntryReopenIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.entries.reopen(user.id, shift_id, body.reason)
    return _one(services, user, shift_id)
