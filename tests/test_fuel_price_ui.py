from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.fuel import Fuel
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.fuel_price_history_repository import FuelPriceHistoryRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.fuel import FuelRateChange
from app.services.auth_service import AuthService
from app.services.fuel_service import FuelService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_fuel_price_ui.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", factory)
    session = factory()
    yield session
    session.close()


def make_user(db_session, role_name: str, username: str) -> User:
    role = db_session.query(Role).filter_by(name=role_name).first()
    user = User(username=username, email=f"{username}@example.com", password_hash=hash_password("Passw0rd!"), role=role, is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_id(db_session):
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def fuel_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return FuelService(FuelRepository(db_session), FuelPriceHistoryRepository(db_session), audit_repo, auth), auth


def petrol(db_session):
    return db_session.query(Fuel).filter_by(fuel_type="Petrol").first()


def test_no_top_level_change_price_button(qapp, db_session, fuel_service, admin_id):
    """2026-09-23 simplification: the top "Change Price" button (select a
    row, then click it) was removed - the per-row edit icon already does
    the same thing in one click, so keeping both was a redundant path."""
    from app.ui.fuel_price_window import FuelPriceWindow

    service, auth_service = fuel_service
    window = FuelPriceWindow(admin_id, service, auth_service)
    assert not hasattr(window, "change_price_button")


def test_row_edit_icon_opens_the_change_price_dialog(qapp, db_session, fuel_service, admin_id):
    from app.ui.fuel_price_window import FuelPriceWindow

    service, auth_service = fuel_service
    window = FuelPriceWindow(admin_id, service, auth_service)

    fuel = petrol(db_session)
    row = next(i for i, f in enumerate(window._fuels) if f.id == fuel.id)
    edit_button = window.table.cellWidget(row, 3)
    assert edit_button is not None

    opened = {}
    window._change_price_for = lambda f: opened.setdefault("fuel_id", f.id)
    edit_button.click()
    assert opened["fuel_id"] == fuel.id


def test_row_edit_icon_hidden_for_view_only_role(qapp, db_session, fuel_service, attendant_id):
    from app.ui.fuel_price_window import FuelPriceWindow

    service, auth_service = fuel_service
    window = FuelPriceWindow(attendant_id, service, auth_service)

    assert window.table.rowCount() > 0
    for row in range(window.table.rowCount()):
        assert window.table.cellWidget(row, 3) is None


def test_change_price_dialog_still_reachable_and_saves(qapp, db_session, fuel_service, admin_id):
    from app.ui.fuel_price_window import FuelRateDialog
    from PySide6.QtWidgets import QDialog

    service, _ = fuel_service
    fuel = petrol(db_session)

    dialog = FuelRateDialog(fuel, admin_id, service, None)
    dialog.rate_input.setValue(105.50)
    dialog.reason_input.setText("Daily OMC revision")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    updated = db_session.query(Fuel).filter_by(id=fuel.id).first()
    assert Decimal(str(updated.rate_per_liter)) == Decimal("105.50")
