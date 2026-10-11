"""Company profile. Same SettingsService calls as app/ui/settings_window.py."""

from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import Out
from api.services import Services
from app.schemas.app_setting import AppSettingUpdate

router = APIRouter(tags=["settings"])


class SettingsOut(Out):
    company_name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gst_number: Optional[str] = None
    licence_number: Optional[str] = None
    receipt_footer: Optional[str] = None
    offsite_backup_dir: Optional[str] = None
    # False = printed documents have no business name on them (the screen warns about it).
    has_company_profile: bool


@router.get("/settings", response_model=SettingsOut)
def get_settings(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.settings.get_settings(user.id)


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    body: AppSettingUpdate, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return services.settings.update_settings(user.id, body)
