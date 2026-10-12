"""Owner-decision settings (rounding rule, credit over limit, ...). Each carries the questionnaire ID it answers."""

from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, Out
from api.services import Services

router = APIRouter(tags=["settings"])


class PumpSettingOut(Out):
    key: str
    value: str
    default: str
    label: str
    help: str
    question_id: str
    choices: Optional[list[str]] = None


class PumpSettingIn(In):
    value: str


def _out(d, value) -> PumpSettingOut:
    return PumpSettingOut(key=d.key, value=value, default=d.default, label=d.label, help=d.help,
                          question_id=d.question_id, choices=list(d.choices) if d.choices else None)


@router.get("/pump-settings", response_model=list[PumpSettingOut])
def list_pump_settings(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [_out(d, v) for d, v in services.pump_settings.list_all(user.id)]


@router.put("/pump-settings/{key}", response_model=PumpSettingOut)
def set_pump_setting(key: str, body: PumpSettingIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    from app.services.pump_settings_service import DEFS

    services.pump_settings.set(user.id, key, body.value)
    return _out(DEFS[key], services.pump_settings.get(key))
