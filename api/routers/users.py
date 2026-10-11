"""User accounts. Same UserService calls as app/ui/user_management_window.py."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services, require_permission
from api.schemas import In, OptionalReason, Out
from api.services import Services
from app.core.constants import Permission
from app.schemas.user import UserCreate

router = APIRouter(tags=["users"])


class UserRow(Out):
    id: str
    username: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role_id: Optional[str] = None
    role: Optional[str] = None
    is_active: bool
    is_locked: bool
    # Same words as the Qt list: Locked wins over Inactive, then Active.
    status: str
    last_login: Optional[datetime] = None


class RoleOut(Out):
    id: str
    name: str


class UserCreateIn(In):
    username: str
    email: str
    password: str
    role_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ChangeRoleIn(In):
    role_id: str
    reason: OptionalReason


class ActiveIn(In):
    is_active: bool
    reason: OptionalReason


class ResetPasswordIn(In):
    new_password: str
    reason: OptionalReason


class ReasonIn(In):
    reason: OptionalReason


class ResetCodeOut(Out):
    code: str


def row(user) -> UserRow:
    status = "Locked" if user.is_locked else ("Inactive" if not user.is_active else "Active")
    return UserRow(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role_id=user.role.id if user.role else None,
        role=user.role.name if user.role else None,
        is_active=user.is_active,
        is_locked=user.is_locked,
        status=status,
        last_login=user.last_login,
    )


def _find(services: Services, actor_id: str, user_id: str) -> UserRow:
    # The Qt dialog re-reads the full list and picks the user; same here.
    for u in services.users.list_users(actor_id):
        if u.id == user_id:
            return row(u)
    from app.core.exceptions import NotFoundError

    raise NotFoundError(f"User not found: {user_id}")


@router.get("/users", response_model=list[UserRow])
def list_users(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [row(u) for u in services.users.list_users(user.id)]


@router.get("/users/roles", response_model=list[RoleOut])
def list_roles(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """Qt fills its role boxes from RoleRepository.list_all(); only user managers see those dialogs."""
    require_permission(services, user.id, Permission.USER_MANAGE)
    return [RoleOut(id=r.id, name=r.name) for r in services.role_repo.list_all()]


@router.post("/users", response_model=UserRow, status_code=201)
def create_user(body: UserCreateIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    created = services.users.create_user(user.id, UserCreate(**body.model_dump()))
    return _find(services, user.id, created.id)


@router.post("/users/{user_id}/role", response_model=UserRow)
def change_role(user_id: str, body: ChangeRoleIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.users.change_user_role(user.id, user_id, body.role_id, body.reason)
    return _find(services, user.id, user_id)


@router.post("/users/{user_id}/active", response_model=UserRow)
def set_active(user_id: str, body: ActiveIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.users.set_user_active(user.id, user_id, body.is_active, body.reason)
    return _find(services, user.id, user_id)


@router.post("/users/{user_id}/unlock", response_model=UserRow)
def unlock(user_id: str, body: ReasonIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.users.unlock_user(user.id, user_id, body.reason)
    return _find(services, user.id, user_id)


@router.post("/users/{user_id}/reset-password", response_model=UserRow)
def reset_password(user_id: str, body: ResetPasswordIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.users.reset_password(user.id, user_id, body.new_password, body.reason)
    return _find(services, user.id, user_id)


@router.post("/users/{user_id}/reset-code", response_model=ResetCodeOut)
def reset_code(user_id: str, body: ReasonIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """The one-time code is returned once and never stored in clear (the service keeps only a hash)."""
    return ResetCodeOut(code=services.users.generate_password_reset_code(user.id, user_id, body.reason))
