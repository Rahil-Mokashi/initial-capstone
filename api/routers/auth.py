"""Login / logout / who-am-I / change-own-password.

AuthService is the only authority; this just carries its answers.
"""

import platform
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user_allow_pending, get_services
from api.errors import ApiError
from api.schemas import ChangePasswordIn, ForgotPasswordIn, LoginIn, LoginOut, ReauthIn, SetPinIn, UserOut
from api.services import Services

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user, last_login: Optional[str] = None) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role.name if user.role else None,
        permissions=sorted(p.name for p in user.role.permissions) if user.role else [],
        must_change_password=bool(user.must_change_password),
        has_pin=user.pin_hash is not None,
        last_login=last_login,
    )


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, services: Services = Depends(get_services)):
    # The device name is what Qt records in the audit log (platform.node()).
    authenticate = services.auth.authenticate_with_pin if body.use_pin else services.auth.authenticate
    ok, data, error = authenticate(body.username, body.password, device_info=platform.node() or "unknown-device")
    if not ok:
        details = data or {}
        code = "account_locked" if "locked_until" in details else "invalid_credentials"
        raise ApiError(401, code, error or "Sign-in failed.", details)
    user = services.user_repo.get_by_id(data["id"])
    return LoginOut(token=data["session_token"], expires_at=data["expires_at"], user=user_out(user, data.get("last_login")))


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser = Depends(current_user_allow_pending)):
    return user_out(current.user)


@router.post("/logout", status_code=204)
def logout(current: CurrentUser = Depends(current_user_allow_pending), services: Services = Depends(get_services)):
    services.auth.logout(current.token)


@router.post("/change-password", response_model=UserOut)
def change_password(
    body: ChangePasswordIn,
    current: CurrentUser = Depends(current_user_allow_pending),
    services: Services = Depends(get_services),
):
    user = services.users.change_own_password(current.id, body.current_password, body.new_password)
    return user_out(user)


@router.post("/reauthenticate", status_code=204)
def reauthenticate(
    body: ReauthIn, current: CurrentUser = Depends(current_user_allow_pending), services: Services = Depends(get_services)
):
    """The lock screen: re-confirm the signed-in person with password or PIN, WITHOUT a new session."""
    ok, error = services.auth.reauthenticate(current.id, body.credential, use_pin=body.use_pin, device_info=platform.node() or "unknown-device")
    if not ok:
        raise ApiError(401, "invalid_credentials", error or "Could not unlock.")


@router.post("/pin", response_model=UserOut)
def set_pin(
    body: SetPinIn, current: CurrentUser = Depends(current_user_allow_pending), services: Services = Depends(get_services)
):
    return user_out(services.users.set_own_pin(current.id, body.current_password, body.pin))


@router.post("/forgot-password", status_code=204)
def forgot_password(body: ForgotPasswordIn, services: Services = Depends(get_services)):
    """Finish an administrator-issued one-time reset code. Needs no session (the person cannot sign in),
    only the launch secret like every other call; every failure carries the same generic message."""
    services.users.reset_password_with_code(body.username.strip(), body.code.strip(), body.new_password)
