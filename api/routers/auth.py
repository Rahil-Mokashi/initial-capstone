"""Login / logout / who-am-I / change-own-password.

AuthService is the only authority; this just carries its answers.
"""

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user_allow_pending, get_services
from api.errors import ApiError
from api.schemas import ChangePasswordIn, LoginIn, LoginOut, UserOut
from api.services import Services

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role.name if user.role else None,
        permissions=sorted(p.name for p in user.role.permissions) if user.role else [],
        must_change_password=bool(user.must_change_password),
    )


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, services: Services = Depends(get_services)):
    ok, data, error = services.auth.authenticate(body.username, body.password, device_info="desktop-app")
    if not ok:
        details = data or {}
        code = "account_locked" if "locked_until" in details else "invalid_credentials"
        raise ApiError(401, code, error or "Sign-in failed.", details)
    user = services.user_repo.get_by_id(data["id"])
    return LoginOut(token=data["session_token"], expires_at=data["expires_at"], user=user_out(user))


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
