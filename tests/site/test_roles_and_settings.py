import pytest

from app.core.constants import ROLE_PERMISSIONS, Permission, UserRole
from app.core.exceptions import PermissionDeniedError


def can(svc, user_id, perm):
    return svc.auth.check_permission(user_id, perm.value)


def test_new_role_and_permissions_are_seeded(svc, uid):
    assert can(svc, uid["DATA_ENTRY"], Permission.SALE_MANAGE)
    assert can(svc, uid["OWNER"], Permission.CHECK_VIEW) and can(svc, uid["ADMIN"], Permission.CHECK_EXPLAIN)


def test_data_entry_is_narrow(svc, uid):
    for perm in (Permission.USER_MANAGE, Permission.ATTENDANCE_MANAGE, Permission.EXPENSE_APPROVE, Permission.SHIFT_REOPEN,
                 Permission.FUEL_PRICE_MANAGE, Permission.SETTINGS_MANAGE, Permission.RECONCILIATION_APPROVE,
                 Permission.CHECK_VIEW, Permission.SHORTAGE_MANAGE, Permission.CREDIT_MANAGE):
        assert not can(svc, uid["DATA_ENTRY"], perm), perm


def test_existing_roles_keep_their_old_permissions():
    # additions only: the accountant is still read-mostly and has no manage rights on shifts or readings
    acc = set(ROLE_PERMISSIONS[UserRole.ACCOUNTANT])
    assert Permission.SHIFT_MANAGE not in acc and Permission.NOZZLE_MANAGE not in acc and Permission.USER_MANAGE not in acc
    assert Permission.EXPENSE_MANAGE in acc


def test_several_owner_logins_are_allowed(db, svc):
    from conftest import make_user

    a, b, c = (make_user(db, UserRole.OWNER.value, n) for n in ("owner_a", "owner_b", "owner_c"))
    assert len({a.id, b.id, c.id}) == 3 and all(u.role.name == "OWNER" for u in (a, b, c))


def test_settings_default_validate_and_audit(svc, uid):
    assert svc.pump_settings.get("rounding_rule") == "per_bill"
    assert svc.pump_settings.get("add_testing_back") == "off"
    assert svc.pump_settings.set(uid["OWNER"], "credit_over_limit", "block") == "block"
    assert svc.pump_settings.get("credit_over_limit") == "block"
    ev = svc.audit_repo.search(event_type="pump_setting_changed")
    assert len(ev) == 1 and "warn -> block" in ev[0].description
    with pytest.raises(ValueError):
        svc.pump_settings.set(uid["OWNER"], "credit_over_limit", "maybe")
    with pytest.raises(ValueError):
        svc.pump_settings.set(uid["OWNER"], "dip_tolerance_percent", "-1")
    with pytest.raises(ValueError):
        svc.pump_settings.set(uid["OWNER"], "nope", "x")
    with pytest.raises(PermissionDeniedError):
        svc.pump_settings.set(uid["DATA_ENTRY"], "credit_over_limit", "warn")
