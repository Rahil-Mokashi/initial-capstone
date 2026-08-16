from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, ShiftStatus, UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.credit_service import CreditService
from app.services.sale_service import SaleService
from app.services.shift_service import ShiftService
from app.services.tank_service import TankService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_sales_ui.db")
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
        username=username, email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"), role=role, is_active=True,
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
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


@pytest.fixture()
def employee_id(db_session):
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add(employee)
    db_session.commit()
    return employee.id


@pytest.fixture()
def fuel_id(db_session):
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=Decimal("100.00"))
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


@pytest.fixture()
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def tank_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return TankService(
        TankRepository(db_session), TankReadingRepository(db_session), TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session), FuelRepository(db_session), EmployeeRepository(db_session),
        audit_repo, auth_service,
    )


@pytest.fixture()
def tank_id(tank_service, admin_id, fuel_id):
    tank = tank_service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=20000.0, opening_stock=10000.0))
    return tank.id


@pytest.fixture()
def nozzle_id(db_session, fuel_id, tank_id):
    dispenser = Dispenser(code="D1", status="active")
    db_session.add(dispenser)
    db_session.commit()
    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel_id, tank_id=tank_id, status="active")
    db_session.add(nozzle)
    db_session.commit()
    return nozzle.id


@pytest.fixture()
def open_shift_id(db_session, admin_id):
    shift = Shift(shift_date=date.today(), shift_label="Morning", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift)
    db_session.commit()
    return shift.id


@pytest.fixture()
def shift_service(db_session, auth_service):
    from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository

    audit_repo = AuditLogRepository(db_session)
    return ShiftService(
        ShiftRepository(db_session), NozzleAssignmentRepository(db_session), EmployeeRepository(db_session),
        NozzleRepository(db_session), UserRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def employee_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return EmployeeService(EmployeeRepository(db_session), None, UserRepository(db_session), None, audit_repo, auth_service)


@pytest.fixture()
def fuel_repo(db_session):
    return FuelRepository(db_session)


@pytest.fixture()
def sale_service(db_session, tank_service, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return SaleService(
        SaleRepository(db_session), ShiftRepository(db_session), NozzleRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), CustomerRepository(db_session),
        TankRepository(db_session), tank_service, audit_repo, auth_service, PaymentRepository(db_session),
        CreditService(
            CreditAccountRepository(db_session), CustomerPaymentRepository(db_session),
            CustomerRepository(db_session), SaleRepository(db_session), audit_repo, auth_service,
        ),
    )


def test_manager_gets_full_picker_and_records_a_sale(
    qapp, sale_service, shift_service, employee_service, fuel_repo, auth_service, admin_id, open_shift_id, nozzle_id, employee_id
):
    from PySide6.QtWidgets import QDialog

    from app.ui.sales_window import SaleFormDialog

    dialog = SaleFormDialog(sale_service, shift_service, employee_service, auth_service, admin_id)
    assert dialog._can_pick_freely is True
    assert dialog.shift_combo.count() == 1
    assert dialog.nozzle_combo.count() == 1

    dialog.quantity_input.setValue(5)
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(sale_service.list_sales(admin_id)) == 1


def test_attendant_gets_self_service_assignment(
    qapp, sale_service, shift_service, employee_service, fuel_repo, auth_service, admin_id, attendant_id, open_shift_id, nozzle_id, employee_id, db_session
):
    from app.models.employee import Employee as EmployeeModel
    from app.models.nozzle_assignment import NozzleAssignment
    from app.core.constants import AssignmentStatus

    attendant_employee = EmployeeModel(
        employee_code="EMP-0002", first_name="Att", last_name="Endant",
        contact_number="9998887777", joining_date=date(2026, 1, 1), user_id=attendant_id,
    )
    db_session.add(attendant_employee)
    db_session.commit()

    assignment = NozzleAssignment(
        employee_id=attendant_employee.id, nozzle_id=nozzle_id, shift_id=open_shift_id,
        opening_meter=100.0, assigned_by_id=admin_id, status=AssignmentStatus.ACTIVE.value,
    )
    db_session.add(assignment)
    db_session.commit()

    from app.ui.sales_window import SaleFormDialog

    dialog = SaleFormDialog(sale_service, shift_service, employee_service, auth_service, attendant_id)
    assert dialog._can_pick_freely is False
    assert dialog._self_service_assignment is not None

    dialog.quantity_input.setValue(5)
    dialog._save()

    from PySide6.QtWidgets import QDialog
    assert dialog.result() == QDialog.Accepted


def test_attendant_without_assignment_shows_error(
    qapp, sale_service, shift_service, employee_service, fuel_repo, auth_service, attendant_id
):
    from app.ui.sales_window import SaleFormDialog

    dialog = SaleFormDialog(sale_service, shift_service, employee_service, auth_service, attendant_id)
    assert dialog._self_service_assignment is None

    dialog._save()
    assert dialog.error_label.isHidden() is False


def test_sales_window_gates_record_button_on_manage_permission(
    qapp, sale_service, shift_service, employee_service, fuel_repo, auth_service, accountant_id
):
    from app.ui.sales_window import SalesWindow

    window = SalesWindow(sale_service, shift_service, employee_service, auth_service, accountant_id)
    assert window.sales_tab.add_button.isHidden() is True
    assert window.customers_tab.add_button.isHidden() is True


def test_sale_row_shows_payment_status(
    qapp, sale_service, shift_service, employee_service, fuel_repo, auth_service, admin_id, open_shift_id, nozzle_id, employee_id
):
    from app.ui.sales_window import SalesTab

    tab = SalesTab(sale_service, shift_service, employee_service, auth_service, admin_id, can_manage=True)
    from app.schemas.sale import SaleCreate
    from app.core.constants import PaymentMethod
    from decimal import Decimal

    sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("5"), payment_method=PaymentMethod.CASH),
    )
    tab.refresh()
    assert tab.table.item(0, 7).text() == "Success"


def test_manage_buttons_hidden_for_view_only_role(
    qapp, sale_service, shift_service, employee_service, fuel_repo, auth_service, accountant_id
):
    from app.ui.sales_window import SalesTab

    tab = SalesTab(sale_service, shift_service, employee_service, auth_service, accountant_id, can_manage=False)
    assert tab.mark_failed_button.isHidden() is True
    assert tab.refund_button.isHidden() is True


def test_export_receipt_writes_a_pdf_file(
    qapp, sale_service, shift_service, employee_service, fuel_repo, auth_service, admin_id, open_shift_id, nozzle_id, employee_id, tmp_path, monkeypatch
):
    from app.schemas.sale import SaleCreate
    from app.ui.sales_window import SalesTab

    sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=Decimal("5"), payment_method=PaymentMethod.CASH),
    )
    tab = SalesTab(sale_service, shift_service, employee_service, auth_service, admin_id, can_manage=True)
    tab.table.selectRow(0)

    target = tmp_path / "receipt.pdf"
    monkeypatch.setattr("app.ui.sales_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(target), "PDF Files (*.pdf)"))
    monkeypatch.setattr("app.ui.sales_window.QMessageBox.information", lambda *a, **k: None)

    tab._export_selected_receipt()

    assert target.exists()


def test_print_receipt_without_selection_shows_info(qapp, sale_service, shift_service, employee_service, fuel_repo, auth_service, admin_id, monkeypatch):
    from app.ui.sales_window import SalesTab

    tab = SalesTab(sale_service, shift_service, employee_service, auth_service, admin_id, can_manage=True)

    called = {}
    monkeypatch.setattr("app.ui.sales_window.QMessageBox.information", lambda *a, **k: called.setdefault("shown", True))

    tab._print_selected_receipt()
    assert called.get("shown") is True


def test_customer_form_creates_customer(qapp, sale_service, admin_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.sales_window import CustomerFormDialog

    dialog = CustomerFormDialog(sale_service, admin_id)
    dialog.name_input.setText("Ravi Transports")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(sale_service.list_customers(admin_id)) == 1
