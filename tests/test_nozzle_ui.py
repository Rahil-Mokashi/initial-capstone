import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import NozzleStatus, UserRole
from app.core.security import hash_password
from app.database.base import Base, StatusEnum
from app.database.seed import seed_initial_data
from app.models.fuel import Fuel
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.dispenser_repository import DispenserRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.nozzle import DispenserCreate, NozzleCreate
from app.services.auth_service import AuthService
from app.services.nozzle_service import NozzleService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_nozzle_ui.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


def make_user(db_session, role_name: str, username: str) -> User:
    role = db_session.query(Role).filter_by(name=role_name).first()
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_id(db_session):
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


@pytest.fixture()
def fuel_repo(db_session):
    return FuelRepository(db_session)


@pytest.fixture()
def fuel_id(db_session):
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=100.0, capacity=10000.0, current_stock=5000.0)
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


@pytest.fixture()
def nozzle_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return NozzleService(
        DispenserRepository(db_session),
        NozzleRepository(db_session),
        FuelRepository(db_session),
        NozzleAssignmentRepository(db_session),
        audit_repo,
        auth_service,
    ), auth_service


def test_add_button_visible_for_manager_hidden_for_view_only(qapp, nozzle_service, admin_id, accountant_id):
    from app.ui.nozzle_window import DispenserTab

    service, _ = nozzle_service

    admin_tab = DispenserTab(service, admin_id, can_manage=True)
    assert admin_tab.add_button.isHidden() is False

    accountant_tab = DispenserTab(service, accountant_id, can_manage=False)
    assert accountant_tab.add_button.isHidden() is True


def test_dispenser_form_saves_valid_dispenser(qapp, nozzle_service, admin_id):
    from app.ui.nozzle_window import DispenserFormDialog
    from PySide6.QtWidgets import QDialog

    service, _ = nozzle_service
    dialog = DispenserFormDialog(service, admin_id)
    dialog.code_input.setText("D1")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(service.list_dispensers(admin_id)) == 1


def test_dispenser_form_rejects_duplicate_code(qapp, nozzle_service, admin_id):
    from app.ui.nozzle_window import DispenserFormDialog

    service, _ = nozzle_service
    service.create_dispenser(admin_id, DispenserCreate(code="D1"))

    dialog = DispenserFormDialog(service, admin_id)
    dialog.code_input.setText("D1")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_dispenser_tab_shows_created_dispensers(qapp, nozzle_service, admin_id):
    from app.ui.nozzle_window import DispenserTab

    service, _ = nozzle_service
    service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    service.create_dispenser(admin_id, DispenserCreate(code="D2"))

    tab = DispenserTab(service, admin_id, can_manage=True)
    assert tab.table.rowCount() == 2


def test_nozzle_form_saves_valid_nozzle(qapp, nozzle_service, fuel_repo, admin_id, fuel_id):
    from app.ui.nozzle_window import NozzleFormDialog
    from PySide6.QtWidgets import QDialog

    service, _ = nozzle_service
    service.create_dispenser(admin_id, DispenserCreate(code="D1"))

    dialog = NozzleFormDialog(service, fuel_repo, admin_id)
    dialog.code_input.setText("N1")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(service.list_nozzles(admin_id)) == 1


def test_nozzle_form_shows_error_when_no_active_dispensers(qapp, nozzle_service, fuel_repo, admin_id, fuel_id):
    from app.ui.nozzle_window import NozzleFormDialog

    service, _ = nozzle_service
    dialog = NozzleFormDialog(service, fuel_repo, admin_id)
    dialog.code_input.setText("N1")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_nozzle_tab_shows_dispenser_and_fuel_columns(qapp, nozzle_service, fuel_repo, admin_id, fuel_id):
    from app.ui.nozzle_window import NozzleTab

    service, _ = nozzle_service
    dispenser = service.create_dispenser(admin_id, DispenserCreate(code="D1"))
    service.create_nozzle(admin_id, NozzleCreate(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id))

    tab = NozzleTab(service, fuel_repo, admin_id, can_manage=True)
    assert tab.table.rowCount() == 1
    assert tab.table.item(0, 1).text() == "D1"
    assert tab.table.item(0, 2).text() == "Petrol"


def test_management_window_tabs_gated_on_manage_permission(qapp, nozzle_service, fuel_repo, admin_id, accountant_id):
    from app.ui.nozzle_window import NozzleManagementWindow

    service, auth_service = nozzle_service

    admin_window = NozzleManagementWindow(service, fuel_repo, auth_service, admin_id)
    assert admin_window.dispenser_tab.add_button.isHidden() is False
    assert admin_window.nozzle_tab.add_button.isHidden() is False

    accountant_window = NozzleManagementWindow(service, fuel_repo, auth_service, accountant_id)
    assert accountant_window.dispenser_tab.add_button.isHidden() is True
    assert accountant_window.nozzle_tab.add_button.isHidden() is True
