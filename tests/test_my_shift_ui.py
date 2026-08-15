from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.employee import EmployeeCreate
from app.schemas.shift import NozzleAssignmentCreate, ShiftOpen
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.shift_service import ShiftService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_my_shift_ui.db")
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
def shift_service(db_session):
    user_repo = UserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(user_repo, audit_repo, UserSessionRepository(db_session))
    return ShiftService(
        ShiftRepository(db_session),
        NozzleAssignmentRepository(db_session),
        EmployeeRepository(db_session),
        NozzleRepository(db_session),
        user_repo,
        audit_repo,
        auth_service,
    ), auth_service


@pytest.fixture()
def nozzle_id(db_session):
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=100.0)
    db_session.add(fuel)
    db_session.commit()

    dispenser = Dispenser(code="D1")
    db_session.add(dispenser)
    db_session.commit()

    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel.id, status="active")
    db_session.add(nozzle)
    db_session.commit()
    return nozzle.id


@pytest.fixture()
def attendant_with_employee(db_session, employee_service, admin_id):
    attendant_user = make_user(db_session, UserRole.ATTENDANT.value, "attendant1")
    employee = employee_service.create_employee(
        admin_id,
        EmployeeCreate(
            first_name="Amit", last_name="Shah", contact_number="9988776655",
            joining_date=date(2026, 1, 1), user_id=attendant_user.id,
        ),
    )
    return attendant_user.id, employee.id


def _all_label_text(window) -> str:
    from PySide6.QtWidgets import QLabel

    return " ".join(label.text() for label in window.findChildren(QLabel))


def test_shows_empty_state_when_no_active_assignment(qapp, shift_service, attendant_with_employee):
    from app.ui.my_shift_window import MyShiftWindow

    service, auth_service = shift_service
    attendant_user_id, _ = attendant_with_employee

    window = MyShiftWindow(service, auth_service, attendant_user_id)
    assert "not currently assigned" in _all_label_text(window)


def test_shows_current_assignment_details(qapp, shift_service, attendant_with_employee, nozzle_id, admin_id):
    from app.ui.my_shift_window import MyShiftWindow

    service, auth_service = shift_service
    attendant_user_id, employee_id = attendant_with_employee

    shift = service.open_shift(admin_id, ShiftOpen(shift_date=date.today(), shift_label="Morning"))
    service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1234.5))

    window = MyShiftWindow(service, auth_service, attendant_user_id)
    text = _all_label_text(window)
    assert "N1" in text
    assert "Petrol" in text
    assert "1234.5" in text


def test_refresh_reflects_new_assignment(qapp, shift_service, attendant_with_employee, nozzle_id, admin_id):
    from app.ui.my_shift_window import MyShiftWindow

    service, auth_service = shift_service
    attendant_user_id, employee_id = attendant_with_employee

    window = MyShiftWindow(service, auth_service, attendant_user_id)
    assert "not currently assigned" in _all_label_text(window)

    shift = service.open_shift(admin_id, ShiftOpen(shift_date=date.today(), shift_label="Morning"))
    service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=500.0))
    window.refresh()

    assert "N1" in _all_label_text(window)
