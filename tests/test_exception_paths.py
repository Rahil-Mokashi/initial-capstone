"""What happens when things go wrong.

Almost every other test in this suite asserts that a correct input
produces a correct result. This one asserts that an INCORRECT input, a
broken dependency, or an outright bug produces a controlled, explainable
failure instead of a crash, a raw traceback, or - worst of all - a silent
wrong answer.

That distinction matters more here than in most software. A crash on a
forecourt PC mid-shift gets the machine rebooted; a raw traceback tells an
attendant nothing and tells an attacker plenty; and a silent wrong answer
in an ERP is indistinguishable from theft.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import app.database.connection  # noqa: F401
import app.models  # noqa: F401
from app.core.constants import PaymentMethod, Permission, ShiftStatus, UserRole
from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import hash_password, verify_password
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
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'exc.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", factory)
    session = factory()
    yield session
    session.close()


@pytest.fixture()
def env(db):
    seed_initial_data()
    role = db.query(Role).filter_by(name=UserRole.MANAGER.value).first()
    user = User(username="mgr", email="m@x.com", password_hash=hash_password("Passw0rd!"),
                role=role, is_active=True)
    db.add(user)
    db.commit()

    audit = AuditLogRepository(db)
    auth = AuthService(UserRepository(db), audit, UserSessionRepository(db))
    tank_service = TankService(
        TankRepository(db), TankReadingRepository(db), TankTransactionRepository(db),
        FuelReconciliationRepository(db), FuelRepository(db), EmployeeRepository(db), audit, auth)
    credit = CreditService(CreditAccountRepository(db), CustomerPaymentRepository(db),
                           CustomerRepository(db), SaleRepository(db), audit, auth)
    payment_repo = PaymentRepository(db)
    sale = SaleService(SaleRepository(db), ShiftRepository(db), NozzleRepository(db),
                       FuelRepository(db), EmployeeRepository(db), CustomerRepository(db),
                       TankRepository(db), tank_service, audit, auth, payment_repo, credit)

    fuel = db.query(Fuel).filter_by(fuel_type="Petrol").first()
    fuel.rate_per_liter = Decimal("100.00")
    db.commit()
    tank = tank_service.create_tank(user.id, TankCreate(
        code="T1", fuel_id=fuel.id, capacity=20000.0, opening_stock=10000.0))
    dispenser = Dispenser(code="D1", status="active")
    employee = Employee(employee_code="EMP-0001", first_name="A", last_name="B",
                        contact_number="9000000000", joining_date=date(2026, 1, 1))
    db.add_all([dispenser, employee])
    db.commit()
    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel.id,
                    tank_id=tank.id, status="active")
    shift = Shift(shift_date=date.today(), shift_label="M", opened_by_id=user.id,
                  status=ShiftStatus.OPEN.value)
    db.add_all([nozzle, shift])
    db.commit()
    return dict(db=db, user_id=user.id, sale=sale, tank=tank_service, auth=auth,
                tank_obj=tank, nozzle_id=nozzle.id, employee_id=employee.id, shift_id=shift.id)


def sale_data(env, **kw):
    base = dict(shift_id=env["shift_id"], nozzle_id=env["nozzle_id"],
                employee_id=env["employee_id"], quantity=Decimal("5"),
                payment_method=PaymentMethod.CASH)
    base.update(kw)
    return SaleCreate(**base)


# =====================================================================
# Every domain failure raises a TYPED error, never a bare Exception
# =====================================================================

@pytest.mark.parametrize("bad_field, value, expected", [
    ("shift_id", "no-such-shift", NotFoundError),
    ("nozzle_id", "no-such-nozzle", NotFoundError),
    ("employee_id", "no-such-employee", NotFoundError),
])
def test_a_dangling_reference_raises_not_found_not_a_crash(env, bad_field, value, expected):
    """The UI distinguishes 'you did something invalid' from 'something is
    broken' by exception type, so the type is load-bearing, not cosmetic."""
    with pytest.raises(expected):
        env["sale"].create_sale(env["user_id"], sale_data(env, **{bad_field: value}))


def test_every_domain_error_is_an_apperror_subclass():
    """The UI catches AppError for a specific, actionable message and falls
    back to a generic one otherwise. An error outside that hierarchy would
    silently be shown as 'something went wrong'."""
    for error_type in (NotFoundError, ConflictError, PermissionDeniedError):
        assert issubclass(error_type, AppError), f"{error_type.__name__} escapes the hierarchy"


def test_a_permission_failure_names_the_permission_not_the_internals(env, db):
    """The message reaches a user, so it must be about what they may do -
    not a stack location or a table name."""
    role = db.query(Role).filter_by(name=UserRole.ATTENDANT.value).first()
    attendant = User(username="att", email="a@x.com", password_hash=hash_password("Passw0rd!"),
                     role=role, is_active=True)
    db.add(attendant)
    db.commit()

    with pytest.raises(PermissionDeniedError) as exc:
        env["tank"].create_tank(attendant.id, TankCreate(
            code="T2", fuel_id=env["tank_obj"].fuel_id, capacity=1000.0, opening_stock=0.0))

    message = str(exc.value)
    assert Permission.INVENTORY_MANAGE.value in message
    for leak in ("Traceback", "sqlalchemy", "self._", ".py:"):
        assert leak not in message, f"internal detail leaked into a user-facing message: {leak}"


# =====================================================================
# A broken dependency fails safely rather than corrupting state
# =====================================================================

def test_a_database_error_midway_leaves_no_partial_sale(env, monkeypatch):
    """Simulates the disk-full / device-lost case rather than a business
    rule violation - the failure is external and unexpected."""
    from app.models.sale import Sale
    from app.models.tank_transaction import TankTransaction

    def explode(*_a, **_k):
        raise OperationalError("INSERT INTO payments", {}, Exception("disk I/O error"))

    monkeypatch.setattr(env["sale"]._payment_repo, "add", explode)

    with pytest.raises(OperationalError):
        env["sale"].create_sale(env["user_id"], sale_data(env))

    env["db"].expire_all()
    assert env["db"].query(Sale).count() == 0
    assert env["db"].query(TankTransaction).count() == 0
    tank = env["tank"].get_tank(env["user_id"], env["tank_obj"].id)
    assert Decimal(str(tank.current_stock)) == Decimal("10000")


def test_the_session_still_works_after_a_failed_operation(env, monkeypatch):
    """A failed write used to leave the shared session's transaction
    aborted, so the NEXT unrelated operation failed too with a confusing
    error masking the real cause."""
    def explode(*_a, **_k):
        raise OperationalError("INSERT INTO payments", {}, Exception("disk I/O error"))

    original = env["sale"]._payment_repo.add
    monkeypatch.setattr(env["sale"]._payment_repo, "add", explode)
    with pytest.raises(OperationalError):
        env["sale"].create_sale(env["user_id"], sale_data(env))

    # Recovery: put the dependency back and carry on.
    monkeypatch.setattr(env["sale"]._payment_repo, "add", original)
    recovered = env["sale"].create_sale(env["user_id"], sale_data(env))
    assert recovered.receipt_number == "RCPT-000001", (
        "the failed attempt consumed a receipt number it never used")


def test_an_unexpected_exception_type_still_rolls_everything_back(env, monkeypatch):
    """The unit of work catches BaseException, not just Exception, because
    a bug can raise anything at all."""
    from app.models.sale import Sale

    class WeirdError(BaseException):
        pass

    monkeypatch.setattr(env["sale"]._payment_repo, "add",
                        lambda *_a, **_k: (_ for _ in ()).throw(WeirdError("bug")))
    with pytest.raises(BaseException):
        env["sale"].create_sale(env["user_id"], sale_data(env))

    env["db"].expire_all()
    assert env["db"].query(Sale).count() == 0


# =====================================================================
# Corrupt or hostile stored data does not crash the reader
# =====================================================================

def test_a_malformed_password_hash_fails_verification_rather_than_raising(env):
    """A truncated or hand-edited hash must be a failed login, not a crash
    that takes the login window with it."""
    for broken in ("", "no-separator", "$", "salt$", "$hash", "a$b$c"):
        assert verify_password("anything", broken) is False


def test_authentication_of_an_unknown_user_does_not_leak_that_fact(env):
    """User enumeration: the response must be identical whether or not the
    account exists."""
    _, _, missing = env["auth"].authenticate("no-such-user", "x")
    _, _, wrong = env["auth"].authenticate("mgr", "WrongPassword!")
    assert missing == wrong


def test_a_null_fuel_rate_cannot_exist_at_all(env, db):
    """Stronger than handling it gracefully: the state is unreachable.

    A NULL rate would raise TypeError deep inside quantity * rate rather
    than being refused at the boundary, so this started as a defensive
    test. It turns out the database will not accept the row in the first
    place - rate_per_liter is NOT NULL - so the defensive path is dead
    code and the invariant is enforced one layer lower, which is where it
    belongs.
    """
    from sqlalchemy.exc import IntegrityError

    fuel = db.query(Fuel).filter_by(fuel_type="Petrol").first()
    fuel.rate_per_liter = None
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_an_unpriced_fuel_is_refused_at_the_service_boundary(env, db):
    """The reachable version of the same concern: 0.00 IS storable (it is
    what seeding writes), so the guard against selling it lives in the
    service rather than in the schema."""
    fuel = db.query(Fuel).filter_by(fuel_type="Petrol").first()
    fuel.rate_per_liter = Decimal("0")
    db.commit()

    with pytest.raises(ConflictError, match="no selling price"):
        env["sale"].create_sale(env["user_id"], sale_data(env))


# =====================================================================
# The UI's last line of defence
# =====================================================================

def test_describe_unexpected_error_returns_a_safe_generic_message():
    """Anything that is not an AppError reaches the user through here, so
    it must never expose internals - a raw traceback tells an attendant
    nothing and an attacker plenty."""
    from app.ui.qt_utils import GENERIC_ERROR_MESSAGE, describe_unexpected_error

    message = describe_unexpected_error(
        RuntimeError("connection to /var/secret/petrol_pump.db failed at 0xDEADBEEF"))
    assert message == GENERIC_ERROR_MESSAGE
    for leak in ("0xDEADBEEF", "/var/secret", "RuntimeError"):
        assert leak not in message


def test_describe_unexpected_error_still_logs_the_real_cause(caplog):
    """Safe for the user must not mean invisible to the developer - the
    full traceback has to reach the log file."""
    import logging

    from app.ui.qt_utils import describe_unexpected_error

    with caplog.at_level(logging.ERROR):
        describe_unexpected_error(ValueError("the real cause, in detail"))
    assert "the real cause, in detail" in caplog.text
