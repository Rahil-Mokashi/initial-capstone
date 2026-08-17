"""Installation-wide settings: the company profile and operational preferences.

This closes a gap that undermined every printed document in the app.
Receipts, statements and reports had no business name, address or GST
number on them, which makes them unusable as customer-facing documents -
a receipt with no identity on it is a slip of paper, not a receipt.

It also unblocks two separately-deferred items by giving them somewhere
to live: a configurable off-device backup location, and (next) print
configuration.
"""

from typing import List

from app.core.constants import Permission
from app.core.permissions import require_permission
from app.models.app_setting import AppSetting
from app.repositories.base import session_for, unit_of_work
from app.schemas.app_setting import AppSettingUpdate


class SettingsService:
    def __init__(self, setting_repo, audit_repo, auth_service):
        self._setting_repo = setting_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(setting_repo)

    @require_permission(Permission.SETTINGS_VIEW.value)
    def get_settings(self, actor_user_id: str) -> AppSetting:
        return self._setting_repo.get_or_create()

    @require_permission(Permission.SETTINGS_MANAGE.value)
    def update_settings(self, actor_user_id: str, data: AppSettingUpdate) -> AppSetting:
        """Change the company profile, recording exactly what changed.

        The old/new snapshot is deliberate: the company profile appears on
        every document the business issues, so "the GST number on last
        month's receipts was different" needs to be answerable.
        """
        with unit_of_work(self._session):
            setting = self._setting_repo.get_or_create()
            changes: List[str] = []

            for field, new_value in data.model_dump().items():
                old_value = getattr(setting, field, None)
                if old_value != new_value:
                    changes.append(f"{field}: {old_value!r} -> {new_value!r}")
                    setattr(setting, field, new_value)

            if not changes:
                return setting

            setting = self._setting_repo.update(setting)
            self._audit_repo.record(
                event_type="settings_updated",
                actor_id=actor_user_id,
                entity_type="AppSetting",
                entity_id=setting.id,
                description="; ".join(changes),
            )
            return setting

    def get_company_profile(self) -> AppSetting:
        """The profile for heading a printed document.

        Undecorated on purpose. Printing a receipt is an action the actor
        is already authorised for under SALE_VIEW; reading the letterhead
        is a side effect of that, not a separate 'view settings' action.
        Re-checking a different permission here is exactly the layering
        mistake TankService's *_as_related_action split exists to avoid.
        """
        return self._setting_repo.get_or_create()
