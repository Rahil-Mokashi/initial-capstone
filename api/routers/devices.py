"""Devices (PCs) allowed to use the Main PC: owner adds one with a pairing code, lists them, removes one.

Thin: the rules live in api.lan.devices. In Single PC mode every call answers 404.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request

from api.deps import CurrentUser, current_user, get_services, require_permission
from api.errors import ApiError
from api.schemas import In, Out
from api.services import Services
from app.core.constants import Permission

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceOut(Out):
    id: str
    name: str
    enrolled_at: datetime
    enrolled_ip: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    last_ip: Optional[str] = None
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None


class PairingCodeOut(Out):
    code: str
    minutes: int
    address: str
    port: int
    pairing_port: int
    ca_fingerprint: str


class DeviceRevokeIn(In):
    reason: str = ""


def _lan(request: Request):
    if request.app.state.lan is None:
        raise ApiError(404, "not_found", "This PC is not the Main PC.")
    return request.app.state.lan


def _allowed(services: Services, user: CurrentUser) -> None:
    require_permission(services, user.id, Permission.DEVICE_MANAGE)


@router.get("", response_model=list[DeviceOut])
def list_devices(request: Request, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    lan = _lan(request)
    _allowed(services, user)
    return lan.devices.list_devices()


@router.post("/pairing", response_model=PairingCodeOut)
def start_pairing(request: Request, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    lan = _lan(request)
    _allowed(services, user)
    code, minutes = lan.start_pairing(user.id)
    services.audit_repo.record("pairing_code_created", actor_id=user.id, description="A device pairing code was created",
                               device_info=lan.describe(request))
    return PairingCodeOut(code=code, minutes=minutes, address=lan.config.bind_address, port=lan.config.port, pairing_port=lan.config.pairing_port,
                          ca_fingerprint=lan.devices.pki.ca_fingerprint())


@router.post("/pairing/cancel", status_code=204)
def cancel_pairing(request: Request, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    lan = _lan(request)
    _allowed(services, user)
    lan.cancel_pairing()


@router.post("/{device_id}/revoke", response_model=DeviceOut)
def revoke(device_id: str, body: DeviceRevokeIn, request: Request, user: CurrentUser = Depends(current_user),
           services: Services = Depends(get_services)):
    lan = _lan(request)
    _allowed(services, user)
    return lan.devices.revoke(device_id, user.id, body.reason)
