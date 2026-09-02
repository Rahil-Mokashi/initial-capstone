from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.dispenser import Dispenser
from app.models.nozzle import Nozzle
from app.models.nozzle_assignment import NozzleAssignment
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.dispenser_repository import DispenserRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.employee import EmployeeCreate
from app.schemas.shift import NozzleAssignmentComplete, NozzleAssignmentCreate, ShiftOpen
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.shift_service import ShiftService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_shift.db")
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
def shift_supervisor_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.SHIFT_SUPERVISOR.value, "supervisor1").id


@pytest.fixture()
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


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
    )


@pytest.fixture()
def employee_id(employee_service, admin_id):
    employee = employee_service.create_employee(
        admin_id,
        EmployeeCreate(first_name="Ravi", last_name="Kumar", contact_number="9876543210", joining_date=date(2026, 1, 1)),
    )
    return employee.id


@pytest.fixture()
def other_employee_id(employee_service, admin_id):
    employee = employee_service.create_employee(
        admin_id,
        EmployeeCreate(first_name="Sita", last_name="Verma", contact_number="9123456780", joining_date=date(2026, 1, 1)),
    )
    return employee.id


@pytest.fixture()
def attendant_with_employee(db_session, employee_service, admin_id):
    """An ATTENDANT-role User whose login is linked to an Employee record —
    the setup needed for the "my assignment" self-service lookup."""
    attendant_user = make_user(db_session, UserRole.ATTENDANT.value, "attendant1")
    employee = employee_service.create_employee(
        admin_id,
        EmployeeCreate(
            first_name="Amit", last_name="Shah", contact_number="9988776655",
            joining_date=date(2026, 1, 1), user_id=attendant_user.id,
        ),
    )
    return attendant_user.id, employee.id


@pytest.fixture()
def nozzle_id(db_session):
    from app.models.fuel import Fuel

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
def other_nozzle_id(db_session, nozzle_id):
    dispenser = db_session.query(Dispenser).first()
    nozzle = Nozzle(code="N2", dispenser_id=dispenser.id, fuel_id=db_session.query(Nozzle).first().fuel_id, status="active")
    db_session.add(nozzle)
    db_session.commit()
    return nozzle.id


def test_open_shift_creates_record(shift_service, admin_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assert shift.status == "open"
    assert shift.shift_label == "Morning"


def test_open_shift_records_audit_log(shift_service, admin_id, db_session):
    shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "shift_opened" in events


def test_duplicate_shift_same_date_and_label_raises_conflict(shift_service, admin_id):
    shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    with pytest.raises(ConflictError):
        shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))


def test_accountant_cannot_open_shift(shift_service, accountant_id):
    with pytest.raises(PermissionDeniedError):
        shift_service.open_shift(accountant_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))


def test_open_shift_unknown_supervisor_raises_not_found(shift_service, admin_id):
    with pytest.raises(NotFoundError):
        shift_service.open_shift(
            admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning", supervisor_id="does-not-exist")
        )


def test_blank_shift_label_rejected_by_schema():
    with pytest.raises(ValidationError):
        ShiftOpen(shift_date=date(2026, 6, 1), shift_label="   ")


def test_assign_nozzle_success(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(
        admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0)
    )
    assert assignment.status == "active"
    assert assignment.opening_meter == 1000.0


def test_cannot_assign_two_employees_to_same_nozzle_in_shift(shift_service, admin_id, employee_id, other_employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    with pytest.raises(ConflictError):
        shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=other_employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))


def test_cannot_assign_same_employee_twice_in_shift(shift_service, admin_id, employee_id, nozzle_id, other_nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    with pytest.raises(ConflictError):
        shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=other_nozzle_id, opening_meter=500.0))


def test_cannot_assign_nozzle_on_closed_shift(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.close_shift(admin_id, shift.id)
    with pytest.raises(ConflictError):
        shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))


def test_complete_nozzle_assignment(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    completed = shift_service.complete_nozzle_assignment(admin_id, assignment.id, NozzleAssignmentComplete(closing_meter=1200.0))
    assert completed.status == "completed"
    assert completed.closing_meter == 1200.0


def test_closing_meter_below_opening_meter_rejected(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    with pytest.raises(ValueError):
        shift_service.complete_nozzle_assignment(admin_id, assignment.id, NozzleAssignmentComplete(closing_meter=999.0))


# --------------------------------------------------------------------
# attach_sale_service / cash auto-settlement on assignment close
# (2026-09-02, user-requested: completing a nozzle assignment should
# auto-settle its remaining cash into one Sale via SaleService, so an
# attendant never has to manually record cash sales one at a time).
# A lightweight fake SaleService is used here rather than a real one -
# SaleService's own settle_assignment_cash logic is already covered in
# tests/test_sale_service.py; what matters here is that ShiftService
# actually calls it (or skips it cleanly when nothing is attached), and
# that the two operations are truly atomic.
# --------------------------------------------------------------------

class _FakeSaleServiceForAssignmentSettlement:
    def __init__(self, raise_error: bool = False):
        self.calls: list[tuple[str, str]] = []
        self._raise_error = raise_error

    def settle_assignment_cash(self, actor_user_id, assignment):
        self.calls.append((actor_user_id, assignment.id))
        if self._raise_error:
            raise RuntimeError("cash settlement failed")


def test_complete_nozzle_assignment_without_attached_sale_service_still_works(shift_service, admin_id, employee_id, nozzle_id):
    """The default, pre-existing behavior - shift_service here never
    calls attach_sale_service, so completing an assignment must work
    exactly as it always has, with the new cash-settlement step simply
    skipped rather than erroring for lack of a wired SaleService."""
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    completed = shift_service.complete_nozzle_assignment(admin_id, assignment.id, NozzleAssignmentComplete(closing_meter=1200.0))
    assert completed.status == "completed"


def test_complete_nozzle_assignment_calls_attached_sale_service(shift_service, admin_id, employee_id, nozzle_id):
    fake_sale_service = _FakeSaleServiceForAssignmentSettlement()
    shift_service.attach_sale_service(fake_sale_service)

    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    completed = shift_service.complete_nozzle_assignment(admin_id, assignment.id, NozzleAssignmentComplete(closing_meter=1200.0))

    assert fake_sale_service.calls == [(admin_id, completed.id)]


def test_complete_nozzle_assignment_rolls_back_if_cash_settlement_fails(shift_service, admin_id, employee_id, nozzle_id, db_session):
    """Proves the unit_of_work wrapping actually does something: a
    failure in the cash-settlement step must not leave the assignment
    half-completed (closing meter recorded but its cash unaccounted
    for) - see CLAUDE.md's "never allow partial financial writes"."""
    fake_sale_service = _FakeSaleServiceForAssignmentSettlement(raise_error=True)
    shift_service.attach_sale_service(fake_sale_service)

    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))

    with pytest.raises(RuntimeError):
        shift_service.complete_nozzle_assignment(admin_id, assignment.id, NozzleAssignmentComplete(closing_meter=1200.0))

    db_session.expire_all()
    refreshed = db_session.query(NozzleAssignment).filter_by(id=assignment.id).first()
    assert refreshed.status == "active"
    assert refreshed.closing_meter is None


def test_close_shift_blocked_while_assignment_active(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    with pytest.raises(ConflictError):
        shift_service.close_shift(admin_id, shift.id)


def test_close_shift_succeeds_after_completing_assignments(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    shift_service.complete_nozzle_assignment(admin_id, assignment.id, NozzleAssignmentComplete(closing_meter=1200.0))
    closed = shift_service.close_shift(admin_id, shift.id)
    assert closed.status == "closed"
    assert closed.closed_by_id == admin_id


def test_cannot_close_already_closed_shift(shift_service, admin_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.close_shift(admin_id, shift.id)
    with pytest.raises(ConflictError):
        shift_service.close_shift(admin_id, shift.id)


def test_reopen_shift_requires_reason(shift_service, admin_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.close_shift(admin_id, shift.id)
    with pytest.raises(ValueError):
        shift_service.reopen_shift(admin_id, shift.id, "")


def test_reopen_shift_by_manager_succeeds_and_audits(shift_service, admin_id, db_session):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.close_shift(admin_id, shift.id)

    reopened = shift_service.reopen_shift(admin_id, shift.id, "Forgot to record an expense")
    assert reopened.status == "open"
    assert reopened.reopen_reason == "Forgot to record an expense"

    events = [log for log in db_session.query(AuditLog).all() if log.event_type == "shift_reopened"]
    assert len(events) == 1


def test_shift_supervisor_cannot_reopen_shift(shift_service, admin_id, shift_supervisor_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.close_shift(admin_id, shift.id)
    with pytest.raises(PermissionDeniedError):
        shift_service.reopen_shift(shift_supervisor_id, shift.id, "Trying to sneak a reopen")


def test_shift_supervisor_can_open_and_close_shifts(shift_service, shift_supervisor_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(shift_supervisor_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(
        shift_supervisor_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0)
    )
    shift_service.complete_nozzle_assignment(shift_supervisor_id, assignment.id, NozzleAssignmentComplete(closing_meter=1100.0))
    closed = shift_service.close_shift(shift_supervisor_id, shift.id)
    assert closed.status == "closed"


def test_cancel_nozzle_assignment_requires_reason(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    with pytest.raises(ValueError):
        shift_service.cancel_nozzle_assignment(admin_id, assignment.id, "")


def test_cancel_nozzle_assignment_frees_up_nozzle_and_employee(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    shift_service.cancel_nozzle_assignment(admin_id, assignment.id, "Wrong employee selected")

    # Should be assignable again now that the previous assignment is cancelled
    new_assignment = shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))
    assert new_assignment.status == "active"


def test_assign_nozzle_unknown_employee_raises_not_found(shift_service, admin_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    with pytest.raises(NotFoundError):
        shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id="does-not-exist", nozzle_id=nozzle_id, opening_meter=0))


def test_list_shifts_and_list_nozzle_assignments(shift_service, admin_id, employee_id, nozzle_id):
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.assign_nozzle(admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0))

    assert len(shift_service.list_shifts(admin_id)) == 1
    assert len(shift_service.list_nozzle_assignments(admin_id, shift.id)) == 1


def test_attendant_with_no_employee_record_sees_no_assignment(shift_service, db_session):
    seed_initial_data()
    lone_attendant = make_user(db_session, UserRole.ATTENDANT.value, "lone_attendant")
    assert shift_service.get_my_active_assignment(lone_attendant.id) is None


def test_attendant_with_employee_but_no_active_assignment_sees_none(shift_service, attendant_with_employee):
    attendant_user_id, _ = attendant_with_employee
    assert shift_service.get_my_active_assignment(attendant_user_id) is None


def test_attendant_sees_their_own_active_assignment(shift_service, admin_id, attendant_with_employee, nozzle_id):
    attendant_user_id, employee_id = attendant_with_employee
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    shift_service.assign_nozzle(
        admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0)
    )

    assignment = shift_service.get_my_active_assignment(attendant_user_id)
    assert assignment is not None
    assert assignment.employee_id == employee_id
    assert assignment.nozzle_id == nozzle_id


def test_attendant_no_longer_sees_completed_assignment(shift_service, admin_id, attendant_with_employee, nozzle_id):
    attendant_user_id, employee_id = attendant_with_employee
    shift = shift_service.open_shift(admin_id, ShiftOpen(shift_date=date(2026, 6, 1), shift_label="Morning"))
    assignment = shift_service.assign_nozzle(
        admin_id, shift.id, NozzleAssignmentCreate(employee_id=employee_id, nozzle_id=nozzle_id, opening_meter=1000.0)
    )
    shift_service.complete_nozzle_assignment(admin_id, assignment.id, NozzleAssignmentComplete(closing_meter=1200.0))

    assert shift_service.get_my_active_assignment(attendant_user_id) is None


def test_shift_supervisor_cannot_use_attendant_self_service_lookup(shift_service, shift_supervisor_id):
    with pytest.raises(PermissionDeniedError):
        shift_service.get_my_active_assignment(shift_supervisor_id)
