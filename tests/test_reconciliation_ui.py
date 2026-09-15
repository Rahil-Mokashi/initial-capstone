from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import ShiftStatus, UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tender_repository import TenderRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService
from app.services.reconciliation_service import ReconciliationService
from app.services.shift_service import ShiftService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_reconciliation_ui.db")
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
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


@pytest.fixture()
def open_shift_id(db_session, admin_id):
    shift = Shift(shift_date=date.today(), shift_label="Morning", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift)
    db_session.commit()
    return shift.id


@pytest.fixture()
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def shift_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ShiftService(
        ShiftRepository(db_session), NozzleAssignmentRepository(db_session), EmployeeRepository(db_session),
        NozzleRepository(db_session), UserRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def reconciliation_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ReconciliationService(
        ShiftReconciliationRepository(db_session), ShiftRepository(db_session),
        SaleRepository(db_session), ExpenseRepository(db_session), audit_repo, auth_service,
        TenderRepository(db_session),
    )


def test_reconciliation_window_gates_manage_buttons_for_view_only_role(
    qapp, reconciliation_service, shift_service, auth_service, accountant_id
):
    from app.ui.reconciliation_window import ReconciliationWindow

    window = ReconciliationWindow(reconciliation_service, shift_service, auth_service, accountant_id)
    assert window.reconciliations_tab.add_button.isHidden() is True
    assert window.reconciliations_tab.approve_button.isHidden() is True


def test_reconciliation_form_reconciles_shift(qapp, reconciliation_service, shift_service, admin_id, open_shift_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.reconciliation_window import ReconciliationFormDialog

    dialog = ReconciliationFormDialog(reconciliation_service, shift_service, admin_id)
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(reconciliation_service.list_reconciliations(admin_id)) == 1


def test_reconciliation_form_builds_one_input_per_tender_with_activity(
    qapp, reconciliation_service, shift_service, admin_id, open_shift_id, db_session,
):
    """End-to-end proof the dynamic per-tender inputs (PROJECT_CONTEXT.md's
    Step 2) actually work through the real dialog, not just the service:
    a shift with a real Cash sale must render exactly one "Declared Cash"
    input, and entering a value through it must reach the resulting
    reconciliation's line."""
    from PySide6.QtWidgets import QDialog

    from app.models.dispenser import Dispenser
    from app.models.employee import Employee
    from app.models.fuel import Fuel
    from app.models.nozzle import Nozzle
    from app.models.sale import Sale
    from app.models.tender import Tender
    from app.ui.reconciliation_window import ReconciliationFormDialog

    fuel = Fuel(fuel_type="Petrol", rate_per_liter=Decimal("100.00"))
    dispenser = Dispenser(code="D1")
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add_all([fuel, dispenser, employee])
    db_session.commit()
    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel.id, status="active")
    db_session.add(nozzle)
    db_session.commit()

    cash_tender = db_session.query(Tender).filter_by(name="Cash").first()
    sale = Sale(
        receipt_number="RCPT-TEST-1", shift_id=open_shift_id, nozzle_id=nozzle.id, fuel_id=fuel.id,
        employee_id=employee.id, quantity=Decimal("10"), rate_per_liter=Decimal("100.00"),
        amount=Decimal("1000.00"), payment_method="cash", tender_id=cash_tender.id,
        status="completed", recorded_by_id=admin_id,
    )
    db_session.add(sale)
    db_session.commit()

    dialog = ReconciliationFormDialog(reconciliation_service, shift_service, admin_id)
    assert list(dialog._tender_inputs.keys()) == [cash_tender.id]
    dialog._tender_inputs[cash_tender.id].setValue(1000.00)

    dialog._save()

    assert dialog.result() == QDialog.Accepted
    reconciliation = reconciliation_service.list_reconciliations(admin_id)[0]
    assert len(reconciliation.lines) == 1
    assert reconciliation.lines[0].tender_id == cash_tender.id
    assert reconciliation.lines[0].variance == Decimal("0.00")
