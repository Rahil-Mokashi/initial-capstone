"""Owner-decision settings with safe defaults (site visit 2026-10-12).

Every business rule the owner has not decided yet is a key here, tagged with
the questionnaire ID it answers, so the code asks the setting instead of
hard-coding a guess. Reading needs SETTINGS_VIEW (or no actor at all for
internal use by the report and check builders); changing needs
OWNER_CHOICE_MANAGE (owners only) and is audit-logged with old and new value.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional, Tuple

from app.core.constants import Permission
from app.core.permissions import require_permission


@dataclass(frozen=True)
class SettingDef:
    key: str
    default: str
    choices: Optional[Tuple[str, ...]]  # None = a non-negative number typed as text
    question_id: str
    label: str
    help: str


_DEFS = [
    SettingDef("rounding_rule", "per_bill", ("per_bill", "per_total"), "T-03/T-04", "Rounding",
               "per_bill: round every bill to paise and add the rounded bills. per_total: add unrounded, round once."),
    SettingDef("add_testing_back", "off", ("on", "off"), "T-01", "Add testing back to stock",
               "Off matches the old report: Testing is shown but not added back to Total Stock."),
    SettingDef("internal_fuel_deducts_tank", "off", ("on", "off"), "T-12", "Internal fuel use also reduces tank stock",
               "Off matches the old report: it already passes through the nozzle meters, so deducting again double-counts."),
    SettingDef("credit_over_limit", "warn", ("warn", "block"), "V-14", "Credit over the limit",
               "warn: allow with a recorded owner override. block: refuse."),
    SettingDef("daily_report_style", "classic", ("classic", "plus"), "T-00", "Daily report style",
               "Classic is the exact copy of the old report; Plus adds checks and extra lines."),
    SettingDef("dip_tolerance_percent", "0.5", None, "T-02", "Dip difference tolerance (%)",
               "A tank whose dip differs from book stock by more than this share of the book is flagged."),
    SettingDef("bank_fee_tolerance_percent", "2.0", None, "H-09", "Bank charge tolerance (%)",
               "How much less than expected a bank credit may be and still count as the same receipt."),
    SettingDef("bank_date_window_days", "4", None, "H-02", "Bank date window (days)",
               "How many days after a sale a bank credit may arrive and still be matched."),
    SettingDef("payroll_leave_paid", "off", ("on", "off"), "U-04", "Approved leave counts as a paid day",
               "Off: salary is prorated by days present only. On: a day of leave is paid."),
    SettingDef("payroll_holiday_paid", "off", ("on", "off"), "U-04", "Holidays count as paid days",
               "Off: salary is prorated by days present only. On: a holiday is paid."),
    SettingDef("payroll_days_basis", "calendar", ("calendar", "30"), "U-04", "Days in a month for proration",
               "calendar: the real days of the month. 30: always thirty."),
    SettingDef("new_customer_approval", "off", ("on", "off"), "V-10", "New credit customers need owner approval",
               "On: a credit customer cannot be sold to until an owner approves them."),
]
DEFS: Dict[str, SettingDef] = {d.key: d for d in _DEFS}


class PumpSettingsService:
    def __init__(self, repo, audit_repo, auth_service):
        self._repo = repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    def get(self, key: str) -> str:
        """Internal read with the default applied; no permission check (report/check builders)."""
        if key not in DEFS:
            raise KeyError(key)
        row = self._repo.get(key)
        return row.value if row else DEFS[key].default

    def get_decimal(self, key: str) -> Decimal:
        return Decimal(self.get(key))

    @require_permission(Permission.SETTINGS_VIEW.value)
    def list_all(self, actor_user_id: str):
        stored = self._repo.all()
        return [(d, stored.get(d.key, d.default)) for d in _DEFS]

    @require_permission(Permission.OWNER_CHOICE_MANAGE.value)
    def set(self, actor_user_id: str, key: str, value: str) -> str:
        d = DEFS.get(key)
        if d is None:
            raise ValueError(f"Unknown setting: {key}")
        value = str(value).strip()
        if d.choices is not None:
            if value not in d.choices:
                raise ValueError(f"{d.label}: choose one of {', '.join(d.choices)}")
        else:
            try:
                if Decimal(value) < 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise ValueError(f"{d.label} must be a number, zero or more") from None
        old = self.get(key)
        if old == value:
            return value
        self._repo.put(key, value, actor_user_id)
        self._audit_repo.record(
            event_type="pump_setting_changed", actor_id=actor_user_id, entity_type="PumpSetting",
            entity_id=key, description=f"{d.label} ({d.question_id}): {old} -> {value}", old_value=old, new_value=value,
        )
        return value
