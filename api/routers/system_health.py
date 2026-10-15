"""System health: is the Main PC safe? (backups, integrity, audit log, off-device copy, disk, PCs). Owners and admins.

Thin: SystemHealthService decides and records. "Run the checks now" runs the same jobs the nightly scheduler runs.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services, require_permission
from api.errors import ApiError
from api.schemas import In, Out
from api.services import Services
from app.core.constants import Permission

router = APIRouter(tags=["system-health"])


class PassphraseIn(In):
    passphrase: str


class HealthRowOut(Out):
    key: str
    name: str
    state: str
    detail: str
    at: Optional[datetime] = None


def _rows(services: Services, user: CurrentUser) -> list[HealthRowOut]:
    return [HealthRowOut.model_validate(r, from_attributes=True) for r in services.system_health.snapshot(user.id)]


@router.get("/system/health", response_model=list[HealthRowOut])
def health(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _rows(services, user)


@router.post("/system/health/run", response_model=list[HealthRowOut])
def run(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    require_permission(services, user.id, Permission.SYSTEM_HEALTH_VIEW)
    services.system_health.run_all()
    return _rows(services, user)


@router.put("/system/backup-passphrase", status_code=204)
def set_backup_passphrase(body: PassphraseIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """Copies that leave the Main PC are encrypted with this. Keep it somewhere safe: without it those copies cannot be opened."""
    require_permission(services, user.id, Permission.SYSTEM_HEALTH_VIEW)
    from api.lan.backup_crypto import BackupCryptoError, check_passphrase
    from api.lan.config import LanConfigError

    if services.secrets is None:
        raise ApiError(422, "not_main_pc", "Encrypted off-device copies are set up on the Main PC.")
    try:
        check_passphrase(body.passphrase)
        services.secrets.set("backup", body.passphrase)
    except (BackupCryptoError, LanConfigError) as exc:
        raise ApiError(422, "cannot_set_passphrase", str(exc))
    services.audit_repo.record("backup_passphrase_set", actor_id=user.id, description="The backup passphrase was changed")
