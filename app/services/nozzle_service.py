"""
Nozzle/Dispenser master-data service layer (problemstatement.md #15,
Phase 8). Phase 7 (Shift Management) built the minimal models and a
read-only path for assignment; this is the actual management surface:
create dispensers/nozzles, and change nozzle status (active/inactive/
maintenance) without ever deleting a row — a retired nozzle is
deactivated, not removed, so its assignment history stays intact.
"""

from typing import List

from app.core.constants import MAX_NOZZLES_PER_DISPENSER, NozzleStatus, Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.models.dispenser import Dispenser
from app.models.nozzle import Nozzle
from app.schemas.nozzle import DispenserCreate, NozzleCreate


class NozzleService:
    def __init__(self, dispenser_repo, nozzle_repo, fuel_repo, assignment_repo, audit_repo, auth_service, tank_repo):
        self._dispenser_repo = dispenser_repo
        self._nozzle_repo = nozzle_repo
        self._fuel_repo = fuel_repo
        self._assignment_repo = assignment_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._tank_repo = tank_repo

    @require_permission(Permission.NOZZLE_MANAGE.value)
    def create_dispenser(self, actor_user_id: str, data: DispenserCreate) -> Dispenser:
        if self._dispenser_repo.get_by_code(data.code):
            raise ConflictError(f"A dispenser with code {data.code!r} already exists")

        dispenser = Dispenser(code=data.code, status=StatusEnum.ACTIVE.value)
        dispenser = self._dispenser_repo.add(dispenser)
        self._audit_repo.record(
            event_type="dispenser_created",
            actor_id=actor_user_id,
            entity_type="Dispenser",
            entity_id=dispenser.id,
            description=f"Created dispenser {data.code}",
        )
        return dispenser

    @require_permission(Permission.NOZZLE_MANAGE.value)
    def set_dispenser_status(self, actor_user_id: str, dispenser_id: str, status: StatusEnum, reason: str) -> Dispenser:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to change a dispenser's status")

        dispenser = self._get_dispenser_or_raise(dispenser_id)
        old_status = dispenser.status
        dispenser.status = status.value
        dispenser = self._dispenser_repo.update(dispenser)
        self._audit_repo.record(
            event_type="dispenser_status_changed",
            actor_id=actor_user_id,
            entity_type="Dispenser",
            entity_id=dispenser.id,
            description=reason.strip(),
            old_value=old_status,
            new_value=status.value,
        )
        return dispenser

    @require_permission(Permission.NOZZLE_VIEW.value)
    def list_dispensers(self, actor_user_id: str) -> List[Dispenser]:
        return self._dispenser_repo.list_all()

    @require_permission(Permission.NOZZLE_MANAGE.value)
    def create_nozzle(self, actor_user_id: str, data: NozzleCreate) -> Nozzle:
        if self._nozzle_repo.get_by_code(data.code):
            raise ConflictError(f"A nozzle with code {data.code!r} already exists")

        dispenser = self._get_dispenser_or_raise(data.dispenser_id)
        if dispenser.status != StatusEnum.ACTIVE.value:
            raise ConflictError(f"Dispenser {dispenser.code} is not active ({dispenser.status})")

        existing_count = self._nozzle_repo.count_for_dispenser(data.dispenser_id)
        if existing_count >= MAX_NOZZLES_PER_DISPENSER:
            raise ConflictError(
                f"Dispenser {dispenser.code} already has {existing_count} nozzles "
                f"(maximum {MAX_NOZZLES_PER_DISPENSER} per dispenser)"
            )

        if not self._fuel_repo.get_by_id(data.fuel_id):
            raise NotFoundError(f"Fuel type not found: {data.fuel_id}")

        if data.tank_id:
            tank = self._tank_repo.get_by_id(data.tank_id)
            if not tank:
                raise NotFoundError(f"Tank not found: {data.tank_id}")
            if tank.fuel_id != data.fuel_id:
                raise ConflictError("The selected tank does not hold this nozzle's fuel type")

        nozzle = Nozzle(
            code=data.code,
            dispenser_id=data.dispenser_id,
            fuel_id=data.fuel_id,
            tank_id=data.tank_id,
            status=NozzleStatus.ACTIVE.value,
        )
        nozzle = self._nozzle_repo.add(nozzle)
        self._audit_repo.record(
            event_type="nozzle_created",
            actor_id=actor_user_id,
            entity_type="Nozzle",
            entity_id=nozzle.id,
            description=f"Created nozzle {data.code} on dispenser {dispenser.code}",
        )
        return nozzle

    @require_permission(Permission.NOZZLE_MANAGE.value)
    def set_nozzle_status(self, actor_user_id: str, nozzle_id: str, status: NozzleStatus, reason: str) -> Nozzle:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to change a nozzle's status")

        nozzle = self._get_nozzle_or_raise(nozzle_id)
        if status != NozzleStatus.ACTIVE and self._assignment_repo.get_active_for_nozzle(nozzle_id):
            raise ConflictError("This nozzle has an active assignment in an open shift and cannot be deactivated")

        old_status = nozzle.status
        nozzle.status = status.value
        nozzle = self._nozzle_repo.update(nozzle)
        self._audit_repo.record(
            event_type="nozzle_status_changed",
            actor_id=actor_user_id,
            entity_type="Nozzle",
            entity_id=nozzle.id,
            description=reason.strip(),
            old_value=old_status,
            new_value=status.value,
        )
        return nozzle

    @require_permission(Permission.NOZZLE_VIEW.value)
    def list_nozzles(self, actor_user_id: str) -> List[Nozzle]:
        return self._nozzle_repo.list_all()

    @require_permission(Permission.NOZZLE_VIEW.value)
    def get_nozzle(self, actor_user_id: str, nozzle_id: str) -> Nozzle:
        return self._get_nozzle_or_raise(nozzle_id)

    def _get_dispenser_or_raise(self, dispenser_id: str) -> Dispenser:
        dispenser = self._dispenser_repo.get_by_id(dispenser_id)
        if not dispenser:
            raise NotFoundError(f"Dispenser not found: {dispenser_id}")
        return dispenser

    def _get_nozzle_or_raise(self, nozzle_id: str) -> Nozzle:
        nozzle = self._nozzle_repo.get_by_id(nozzle_id)
        if not nozzle:
            raise NotFoundError(f"Nozzle not found: {nozzle_id}")
        return nozzle
