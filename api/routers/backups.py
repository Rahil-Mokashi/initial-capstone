"""Backups. Same BackupService calls as app/ui/backup_window.py.

A backup is named by its file name only, resolved against the service's own list, so a caller can
never point the restore or copy at an arbitrary path on disk."""

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.errors import ApiError
from api.schemas import In, OptionalReason, Out
from api.services import Services
from app.core.constants import OFFSITE_BACKUP_STALE_AFTER_DAYS
from app.database import backup as backup_module

router = APIRouter(tags=["backups"])


class BackupOut(Out):
    filename: str
    size_bytes: int
    created_at: datetime


class OffsiteStatus(Out):
    # never = no destination known yet; unreachable; stale; ok
    state: str
    destination: Optional[str] = None
    age_days: Optional[float] = None
    stale_after_days: int = OFFSITE_BACKUP_STALE_AFTER_DAYS


class BackupListOut(Out):
    backups: list[BackupOut]
    offsite: OffsiteStatus
    configured_offsite_dir: Optional[str] = None


class IntegrityOut(Out):
    ok: bool
    messages: list[str]


class CopyIn(In):
    destination_dir: str


class CopyOut(Out):
    destination: str
    offsite: OffsiteStatus


class RestoreIn(In):
    reason: OptionalReason


def _out(info) -> BackupOut:
    return BackupOut(filename=info.filename, size_bytes=info.size_bytes, created_at=info.created_at)


def _offsite(destination: Optional[str]) -> OffsiteStatus:
    """Same decision as BackupWindow._refresh_offsite_warning."""
    if not destination:
        return OffsiteStatus(state="never")
    age = backup_module.latest_offsite_copy_age_days(destination)
    if age is None:
        return OffsiteStatus(state="unreachable", destination=destination)
    if age > OFFSITE_BACKUP_STALE_AFTER_DAYS:
        return OffsiteStatus(state="stale", destination=destination, age_days=age)
    return OffsiteStatus(state="ok", destination=destination, age_days=age)


def _find(services: Services, user_id: str, filename: str):
    for info in services.backups.list_backups(user_id):
        if info.filename == filename:
            return info
    raise ApiError(404, "not_found", "That backup no longer exists.")


@router.get("/backups", response_model=BackupListOut)
def list_backups(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    items = services.backups.list_backups(user.id)
    configured = services.settings.get_company_profile().offsite_backup_dir
    return BackupListOut(
        backups=[_out(i) for i in items], offsite=_offsite(configured), configured_offsite_dir=configured
    )


@router.post("/backups", response_model=BackupOut, status_code=201)
def create_backup(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _out(services.backups.create_backup(user.id))


@router.post("/backups/check", response_model=IntegrityOut)
def check_integrity(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    ok, messages = services.backups.check_integrity(user.id)
    return IntegrityOut(ok=ok, messages=messages)


@router.post("/backups/{filename}/copy", response_model=CopyOut)
def copy_offsite(
    filename: str, body: CopyIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    info = _find(services, user.id, filename)
    destination = services.backups.copy_backup_offsite(user.id, info.path, body.destination_dir)
    return CopyOut(destination=str(destination), offsite=_offsite(os.path.dirname(str(destination))))


@router.post("/backups/{filename}/restore", status_code=204)
def restore(
    filename: str, body: RestoreIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    info = _find(services, user.id, filename)
    services.backups.restore_backup(user.id, info.path, body.reason)
