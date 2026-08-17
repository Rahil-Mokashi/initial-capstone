"""Company profile and installation-wide settings.

Exists because every printed document carried no business identity - a
receipt with no pump name, address or GST number cannot be handed to a
customer.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database.connection  # noqa: F401
import app.models  # noqa: F401
from app.core.constants import UserRole
from app.core.exceptions import PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.repositories.app_setting_repository import AppSettingRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.app_setting import AppSettingUpdate
from app.services.auth_service import AuthService
from app.services.settings_service import SettingsService


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'set.db'}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", factory)
    session = factory()
    yield session
    session.close()


def make_user(db, role_name, username):
    role = db.query(Role).filter_by(name=role_name).first()
    user = User(username=username, email=f"{username}@x.com",
                password_hash=hash_password("Passw0rd!"), role=role, is_active=True)
    db.add(user)
    db.commit()
    return user.id


@pytest.fixture()
def manager_id(db):
    seed_initial_data()
    return make_user(db, UserRole.MANAGER.value, "mgr")


@pytest.fixture()
def attendant_id(db):
    seed_initial_data()
    return make_user(db, UserRole.ATTENDANT.value, "att")


@pytest.fixture()
def service(db):
    audit = AuditLogRepository(db)
    auth = AuthService(UserRepository(db), audit, UserSessionRepository(db))
    return SettingsService(AppSettingRepository(db), audit, auth)


# ---------------------------------------------------------------------

def test_settings_are_created_on_first_read(db, manager_id, service):
    """Creating on read rather than at seed time means an existing
    installation upgrading into this feature needs no data migration."""
    setting = service.get_settings(manager_id)
    assert setting is not None
    assert setting.has_company_profile is False


def test_only_one_settings_row_ever_exists(db, manager_id, service):
    from app.models.app_setting import AppSetting

    service.get_settings(manager_id)
    service.get_settings(manager_id)
    service.update_settings(manager_id, AppSettingUpdate(company_name="Shree Petroleum"))
    assert db.query(AppSetting).count() == 1


def test_a_manager_can_save_the_company_profile(db, manager_id, service):
    saved = service.update_settings(manager_id, AppSettingUpdate(
        company_name="Shree Petroleum Services",
        address_line1="Nashik Road",
        city="Nashik", state="Maharashtra", postal_code="422101",
        phone="0253 2451234", gst_number="27AAPFU0939F1ZV"))

    assert saved.company_name == "Shree Petroleum Services"
    assert saved.gst_number == "27AAPFU0939F1ZV"
    assert saved.has_company_profile is True


def test_the_address_prints_as_tidy_lines(db, manager_id, service):
    saved = service.update_settings(manager_id, AppSettingUpdate(
        company_name="X", address_line1="Nashik Road", city="Nashik",
        state="Maharashtra", postal_code="422101"))
    assert saved.address_lines() == ["Nashik Road", "Nashik, Maharashtra - 422101"]


def test_empty_address_parts_are_skipped_rather_than_printing_blank_lines(db, manager_id, service):
    saved = service.update_settings(manager_id, AppSettingUpdate(
        company_name="X", address_line1="Nashik Road"))
    assert saved.address_lines() == ["Nashik Road"]


def test_a_change_is_audit_logged_with_the_old_and_new_values(db, manager_id, service):
    """The company profile appears on every document the business issues,
    so a question about what the GST number was last month has to be
    answerable."""
    service.update_settings(manager_id, AppSettingUpdate(company_name="Old Name"))
    service.update_settings(manager_id, AppSettingUpdate(company_name="New Name"))

    events = db.query(AuditLog).filter_by(event_type="settings_updated").all()
    assert len(events) == 2
    assert "Old Name" in events[1].description
    assert "New Name" in events[1].description


def test_saving_with_nothing_changed_writes_no_audit_noise(db, manager_id, service):
    """Opening settings and clicking Save must not fill the trail with
    entries recording that nothing happened."""
    service.update_settings(manager_id, AppSettingUpdate(company_name="Same"))
    service.update_settings(manager_id, AppSettingUpdate(company_name="Same"))
    assert db.query(AuditLog).filter_by(event_type="settings_updated").count() == 1


# --- validation -------------------------------------------------------

def test_a_blank_field_is_stored_as_not_set(db, manager_id, service):
    """A cleared text box and a never-filled one must behave identically."""
    service.update_settings(manager_id, AppSettingUpdate(company_name="X", city="Nashik"))
    saved = service.update_settings(manager_id, AppSettingUpdate(company_name="X", city="   "))
    assert saved.city is None


@pytest.mark.parametrize(
    "bad_gst", ["123", "27AAPFU0939F1Z", "27AAPFU0939F1ZVX", "27AAPFU-939F1ZV"]
)
def test_a_malformed_gst_number_is_rejected(bad_gst):
    with pytest.raises(ValueError):
        AppSettingUpdate(gst_number=bad_gst)


def test_a_gst_number_is_stored_uppercase(db, manager_id, service):
    saved = service.update_settings(manager_id, AppSettingUpdate(gst_number="27aapfu0939f1zv"))
    assert saved.gst_number == "27AAPFU0939F1ZV"


@pytest.mark.parametrize("bad_email", ["notanemail", "no@domain", "@x.com"])
def test_a_malformed_email_is_rejected(bad_email):
    with pytest.raises(ValueError):
        AppSettingUpdate(email=bad_email)


def test_a_too_short_phone_is_rejected():
    with pytest.raises(ValueError):
        AppSettingUpdate(phone="123")


def test_optional_fields_may_all_be_left_empty():
    """Blocking the whole form on one missing field is how settings screens
    end up never being filled in at all."""
    assert AppSettingUpdate().company_name is None


# --- permissions ------------------------------------------------------

def test_an_attendant_can_read_settings_but_not_change_them(db, attendant_id, service):
    """VIEW is granted widely because printing a receipt needs the
    letterhead whoever prints it."""
    service.get_settings(attendant_id)
    with pytest.raises(PermissionDeniedError):
        service.update_settings(attendant_id, AppSettingUpdate(company_name="Nope"))


def test_the_printing_helper_needs_no_permission_of_its_own(db, manager_id, service):
    """get_company_profile is a side effect of printing, which the actor is
    already authorised for - re-checking a different permission here is the
    layering bug that TankService's related-action split exists to avoid."""
    service.update_settings(manager_id, AppSettingUpdate(company_name="Shree Petroleum"))
    assert service.get_company_profile().company_name == "Shree Petroleum"
