from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import AssignmentStatus, PaymentMethod, ShiftStatus, UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.nozzle_assignment import NozzleAssignment
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
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
from app.services.credit_service import CreditService
from app.services.employee_service import EmployeeService
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
    sqlite_path = str(tmp_path / "test_terminal_ui.db")
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
def employee_id(db_session):
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add(employee)
    db_session.commit()
    return employee.id


@pytest.fixture()
def shift_service(db_session, auth_service):
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


def test_manager_gets_nozzle_chips_and_records_a_sale(
    qapp, sale_service, shift_service, employee_service, auth_service, admin_id, open_shift_id, nozzle_id, employee_id
):
    from app.ui.terminal_window import TerminalWindow

    window = TerminalWindow(sale_service, shift_service, employee_service, auth_service, admin_id)
    assert window._can_pick_freely is True
    assert len(window._nozzle_chips) == 1
    assert window._nozzle_chips[0].isChecked() is True

    window._amount_input.setValue(500)  # rupee mode is the default
    window._submit()

    # isVisible() reflects actual on-screen visibility, which requires the
    # whole window to have been shown - isHidden() reflects the explicit
    # setVisible() flag this test cares about, same as the rest of this
    # app's UI tests (e.g. test_sales_ui.py's button-visibility checks).
    assert window._confirmation_card.isHidden() is False
    sales = sale_service.list_sales(admin_id)
    assert len(sales) == 1
    assert sales[0].quantity == Decimal("5.00")  # 500 / 100 per litre


def test_attendant_self_service_resolves_assignment_and_records_a_sale(
    qapp, sale_service, shift_service, employee_service, auth_service,
    admin_id, attendant_id, open_shift_id, nozzle_id, db_session
):
    attendant_employee = Employee(
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

    from app.ui.terminal_window import TerminalWindow

    window = TerminalWindow(sale_service, shift_service, employee_service, auth_service, attendant_id)
    assert window._can_pick_freely is False
    assert window._assignment is not None
    assert window._submit_button.isEnabled() is True

    window._liters_chip.setChecked(True)
    window._amount_input.setValue(10)
    window._submit()

    # isVisible() reflects actual on-screen visibility, which requires the
    # whole window to have been shown - isHidden() reflects the explicit
    # setVisible() flag this test cares about, same as the rest of this
    # app's UI tests (e.g. test_sales_ui.py's button-visibility checks).
    assert window._confirmation_card.isHidden() is False
    sales = sale_service.list_sales(attendant_id)
    assert len(sales) == 1
    assert sales[0].quantity == Decimal("10")
    assert sales[0].amount == Decimal("1000.00")


def test_attendant_without_assignment_disables_submit(
    qapp, sale_service, shift_service, employee_service, auth_service, attendant_id
):
    from app.ui.terminal_window import TerminalWindow

    window = TerminalWindow(sale_service, shift_service, employee_service, auth_service, attendant_id)
    assert window._assignment is None
    assert window._submit_button.isEnabled() is False


def test_rupee_preset_sets_amount_and_updates_preview(
    qapp, sale_service, shift_service, employee_service, auth_service, admin_id, open_shift_id, nozzle_id, employee_id
):
    from app.ui.terminal_window import TerminalWindow

    window = TerminalWindow(sale_service, shift_service, employee_service, auth_service, admin_id)
    window._apply_preset(1000)

    assert window._rupee_chip.isChecked() is True
    assert window._amount_input.value() == 1000
    assert "10.00 L" in window._preview_label.text()
    assert "1,000.00" in window._preview_label.text()


def test_unpriced_fuel_blocks_submit_with_a_clear_message(
    qapp, sale_service, shift_service, employee_service, auth_service, admin_id, db_session, tank_service
):
    unpriced_fuel = Fuel(fuel_type="Diesel", rate_per_liter=Decimal("0"))
    db_session.add(unpriced_fuel)
    db_session.commit()
    tank = tank_service.create_tank(admin_id, TankCreate(code="T2", fuel_id=unpriced_fuel.id, capacity=20000.0, opening_stock=5000.0))
    dispenser = Dispenser(code="D2", status="active")
    db_session.add(dispenser)
    db_session.commit()
    nozzle = Nozzle(code="N2", dispenser_id=dispenser.id, fuel_id=unpriced_fuel.id, tank_id=tank.id, status="active")
    db_session.add(nozzle)
    db_session.commit()

    shift = Shift(shift_date=date.today(), shift_label="Morning", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift)
    db_session.commit()

    employee = Employee(
        employee_code="EMP-9001", first_name="A", last_name="B",
        contact_number="9000000000", joining_date=date(2026, 1, 1),
    )
    db_session.add(employee)
    db_session.commit()

    from app.ui.terminal_window import TerminalWindow

    window = TerminalWindow(sale_service, shift_service, employee_service, auth_service, admin_id)
    for chip in window._nozzle_chips:
        if chip.data.code == "N2":
            chip.setChecked(True)

    window._submit()

    assert window._error_label.isHidden() is False
    assert "no selling price" in window._error_label.text()
    assert sale_service.list_sales(admin_id) == []
