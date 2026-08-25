from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import TankTransactionType, UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.employee import EmployeeCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.tank_service import TankService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_tank_ui.db")
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
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=100.0)
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


@pytest.fixture()
def employee_service(db_session):
    user_repo = UserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(user_repo, audit_repo, UserSessionRepository(db_session))
    return EmployeeService(
        EmployeeRepository(db_session),
        EmployeeDocumentRepository(db_session),
        user_repo,
        RoleRepository(db_session),
        audit_repo,
        auth_service,
    )


@pytest.fixture()
def tank_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return TankService(
        TankRepository(db_session),
        TankReadingRepository(db_session),
        TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session),
        FuelRepository(db_session),
        EmployeeRepository(db_session),
        audit_repo,
        auth_service,
    ), auth_service


@pytest.fixture()
def employee_id(employee_service, admin_id):
    employee = employee_service.create_employee(
        admin_id,
        EmployeeCreate(first_name="Ravi", last_name="Kumar", contact_number="9876543210", joining_date=date(2026, 1, 1)),
    )
    return employee.id


def test_add_button_visible_for_manager_hidden_for_view_only(qapp, tank_service, admin_id, accountant_id):
    from app.ui.tank_window import TankListWindow

    service, auth_service = tank_service

    admin_window = TankListWindow(service, None, None, auth_service, admin_id)
    assert admin_window.add_button.isHidden() is False

    accountant_window = TankListWindow(service, None, None, auth_service, accountant_id)
    assert accountant_window.add_button.isHidden() is True


def test_tank_form_saves_valid_tank(qapp, tank_service, fuel_repo, admin_id, fuel_id):
    from app.ui.tank_window import TankFormDialog
    from PySide6.QtWidgets import QDialog

    service, _ = tank_service
    dialog = TankFormDialog(service, fuel_repo, admin_id)
    dialog.code_input.setText("T1")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(service.list_tanks(admin_id)) == 1


def test_tank_form_rejects_duplicate_code(qapp, tank_service, fuel_repo, admin_id, fuel_id):
    from app.ui.tank_window import TankFormDialog

    service, _ = tank_service
    service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=10000.0))

    dialog = TankFormDialog(service, fuel_repo, admin_id)
    dialog.code_input.setText("T1")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_tank_list_shows_created_tanks(qapp, tank_service, admin_id, fuel_id):
    from app.ui.tank_window import TankListWindow

    service, auth_service = tank_service
    service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=10000.0, opening_stock=5000.0))

    window = TankListWindow(service, None, None, auth_service, admin_id)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 0).text() == "T1"
    # The gauge grid is a second, independent rendering of the same
    # tank list (see TankGaugeCard) - it must stay in sync with the
    # table on every refresh, not just at construction.
    assert window._gauge_grid.count() == 1


def test_gauge_grid_rebuilds_on_refresh(qapp, tank_service, admin_id, fuel_id):
    from app.ui.tank_window import TankListWindow

    service, auth_service = tank_service
    window = TankListWindow(service, None, None, auth_service, admin_id)
    assert window._gauge_grid.count() == 0

    service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=10000.0, opening_stock=5000.0))
    window.refresh()
    assert window._gauge_grid.count() == 1

    service.create_tank(admin_id, TankCreate(code="T2", fuel_id=fuel_id, capacity=8000.0, opening_stock=1000.0))
    window.refresh()
    assert window._gauge_grid.count() == 2


def test_recent_transactions_panel_shows_empty_state_then_a_recorded_transaction(qapp, tank_service, admin_id, fuel_id):
    from app.ui.tank_window import TankListWindow

    service, auth_service = tank_service
    window = TankListWindow(service, None, None, auth_service, admin_id)

    from PySide6.QtWidgets import QLabel

    def panel_texts():
        return [label.text() for label in window._recent_panel.findChildren(QLabel)]

    assert any("No transactions recorded yet" in text for text in panel_texts())

    tank = service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=10000.0, opening_stock=1000.0))
    from app.schemas.tank import TankTransactionCreate

    service.record_transaction(admin_id, tank.id, TankTransactionType.RECEIPT, TankTransactionCreate(quantity=250.0))
    window.refresh()

    texts = panel_texts()
    assert any("Receipt" in text and "T1" in text for text in texts)
    assert any("+250" in text for text in texts)


def test_detail_dialog_record_receipt_and_reconcile(qapp, tank_service, employee_service, admin_id, fuel_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.tank_window import ReconciliationDialog, TankDetailDialog, TankTransactionDialog

    service, auth_service = tank_service
    tank = service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=10000.0, opening_stock=1000.0))

    receipt_dialog = TankTransactionDialog(service, admin_id, tank.id, TankTransactionType.RECEIPT)
    receipt_dialog.quantity_input.setValue(500.0)
    receipt_dialog._save()
    assert receipt_dialog.result() == QDialog.Accepted
    assert service.get_tank(admin_id, tank.id).current_stock == 1500.0

    detail = TankDetailDialog(service, employee_service, auth_service, admin_id, tank.id)
    assert detail.transactions_table.rowCount() == 1

    # Before any reconciliation exists, the variance card has nothing to
    # show - no card, not an empty/placeholder one.
    assert detail._variance_card_slot.count() == 0

    reconcile_dialog = ReconciliationDialog(service, admin_id, tank.id)
    reconcile_dialog.physical_stock_input.setValue(1500.0)
    reconcile_dialog._save()
    assert reconcile_dialog.result() == QDialog.Accepted

    # The variance card is a second, independent rendering of the same
    # latest-reconciliation figures already in the table - it must
    # appear the moment a reconciliation exists, on refresh.
    detail._refresh()
    assert detail._variance_card_slot.count() == 1


def test_reading_dialog_does_not_change_book_stock(qapp, tank_service, employee_service, admin_id, fuel_id, employee_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.tank_window import TankReadingDialog

    service, _ = tank_service
    tank = service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=10000.0, opening_stock=1000.0))

    dialog = TankReadingDialog(service, employee_service, admin_id, tank.id)
    dialog.physical_stock_input.setValue(950.0)
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert service.get_tank(admin_id, tank.id).current_stock == 1000.0


def test_transaction_dialog_shows_generic_message_on_unexpected_error(qapp, tank_service, admin_id, fuel_id, monkeypatch):
    from app.ui.tank_window import TankTransactionDialog

    service, _ = tank_service
    tank = service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=10000.0))

    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(service, "record_transaction", boom)

    dialog = TankTransactionDialog(service, admin_id, tank.id, TankTransactionType.RECEIPT)
    dialog.quantity_input.setValue(100.0)
    dialog._save()

    assert "Something went wrong" in dialog.error_label.text()
