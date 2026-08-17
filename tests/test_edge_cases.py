"""Edge cases and rule interactions, hunting for logic errors.

Every other suite tests one service doing the thing it is for. This one
probes the seams: what happens at exact boundaries, what happens when an
action is repeated, and whether a reversal in one module correctly
propagates to another. That is where logic errors actually live - the
individual rules are usually right, and the bugs are in how two right
rules combine.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database.connection  # noqa: F401  (installs the FK/WAL pragma listener)
import app.models  # noqa: F401
from app.core.constants import PaymentMethod, PaymentStatus, SaleStatus, ShiftStatus, UserRole
from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.customer_payment import CustomerPayment
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
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.credit import CreditAccountCreate
from app.schemas.customer import CustomerCreate
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.reconciliation_service import ReconciliationService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'edge.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", factory)
    session = factory()
    yield session
    session.close()


@pytest.fixture()
def env(db):
    """One fully wired environment, built the way AppController does."""
    seed_initial_data()
    role = db.query(Role).filter_by(name=UserRole.MANAGER.value).first()
    user = User(username="mgr", email="mgr@x.com", password_hash=hash_password("Passw0rd!"),
                role=role, is_active=True)
    db.add(user)
    db.commit()

    audit = AuditLogRepository(db)
    auth = AuthService(UserRepository(db), audit, UserSessionRepository(db))
    tank_service = TankService(
        TankRepository(db), TankReadingRepository(db), TankTransactionRepository(db),
        FuelReconciliationRepository(db), FuelRepository(db), EmployeeRepository(db), audit, auth)
    credit_service = CreditService(
        CreditAccountRepository(db), CustomerPaymentRepository(db),
        CustomerRepository(db), SaleRepository(db), audit, auth)
    payment_repo = PaymentRepository(db)
    sale_service = SaleService(
        SaleRepository(db), ShiftRepository(db), NozzleRepository(db), FuelRepository(db),
        EmployeeRepository(db), CustomerRepository(db), TankRepository(db), tank_service,
        audit, auth, payment_repo, credit_service)
    reconciliation_service = ReconciliationService(
        ShiftReconciliationRepository(db), ShiftRepository(db), SaleRepository(db),
        ExpenseRepository(db), audit, auth)

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
    shift = Shift(shift_date=date.today(), shift_label="Morning",
                  opened_by_id=user.id, status=ShiftStatus.OPEN.value)
    db.add_all([nozzle, shift])
    db.commit()

    return dict(db=db, user_id=user.id, sale=sale_service, tank=tank_service,
                credit=credit_service, recon=reconciliation_service, payment_repo=payment_repo,
                fuel=fuel, tank_obj=tank, nozzle_id=nozzle.id, employee_id=employee.id,
                shift_id=shift.id)


def sale_data(env, **kw):
    base = dict(shift_id=env["shift_id"], nozzle_id=env["nozzle_id"],
                employee_id=env["employee_id"], quantity=Decimal("10"),
                payment_method=PaymentMethod.CASH)
    base.update(kw)
    return SaleCreate(**base)


def make_credit_customer(env, limit="5000"):
    customer = env["sale"].create_customer(env["user_id"], CustomerCreate(
        name="Acme Transport", contact_number="9876543210"))
    env["credit"].create_credit_account(env["user_id"], CreditAccountCreate(
        customer_id=customer.id, credit_limit=Decimal(limit), payment_due_days=30))
    return customer


# =====================================================================
# Reversal propagation: does undoing one thing undo everything it touched?
# =====================================================================

def test_cancelling_a_credit_sale_frees_the_credit_back_up(env):
    customer = make_credit_customer(env, "5000")
    s = env["sale"].create_sale(env["user_id"], sale_data(
        env, quantity=Decimal("40"), payment_method=PaymentMethod.CREDIT, customer_id=customer.id))
    assert env["credit"].get_outstanding_balance(env["user_id"], customer.id) == Decimal("4000")

    env["sale"].cancel_sale(env["user_id"], s.id, "Customer drove off")
    assert env["credit"].get_outstanding_balance(env["user_id"], customer.id) == Decimal("0")

    # And the freed credit is genuinely usable again.
    env["sale"].create_sale(env["user_id"], sale_data(
        env, quantity=Decimal("40"), payment_method=PaymentMethod.CREDIT, customer_id=customer.id))


def test_cancelling_a_sale_returns_the_fuel_to_the_tank(env):
    before = Decimal(str(env["tank"].get_tank(env["user_id"], env["tank_obj"].id).current_stock))
    s = env["sale"].create_sale(env["user_id"], sale_data(env, quantity=Decimal("25")))
    env["sale"].cancel_sale(env["user_id"], s.id, "Wrong nozzle")
    after = Decimal(str(env["tank"].get_tank(env["user_id"], env["tank_obj"].id).current_stock))
    assert after == before


def test_a_sale_cannot_be_cancelled_twice(env):
    s = env["sale"].create_sale(env["user_id"], sale_data(env))
    env["sale"].cancel_sale(env["user_id"], s.id, "First")
    with pytest.raises(ConflictError):
        env["sale"].cancel_sale(env["user_id"], s.id, "Second")


def test_a_cancelled_sales_payment_cannot_then_be_refunded(env):
    """Double-reversal guard: the payment is already REVERSED, so refunding
    it would take the money out twice."""
    s = env["sale"].create_sale(env["user_id"], sale_data(env))
    env["sale"].cancel_sale(env["user_id"], s.id, "Cancelled")
    payment = env["payment_repo"].get_by_sale_id(s.id)
    assert payment.status == PaymentStatus.REVERSED.value
    with pytest.raises(ConflictError):
        env["sale"].refund_payment(env["user_id"], payment.id, "Refund too")


def test_a_refunded_payment_cannot_be_refunded_again(env):
    s = env["sale"].create_sale(env["user_id"], sale_data(env))
    payment = env["payment_repo"].get_by_sale_id(s.id)
    env["sale"].refund_payment(env["user_id"], payment.id, "Card dispute")
    with pytest.raises(ConflictError):
        env["sale"].refund_payment(env["user_id"], payment.id, "Again")


# =====================================================================
# Exact boundaries
# =====================================================================

def test_a_sale_landing_exactly_on_the_credit_limit_is_allowed(env):
    """Off-by-one: the limit is a ceiling the balance may reach, not pass."""
    customer = make_credit_customer(env, "1000")
    env["sale"].create_sale(env["user_id"], sale_data(
        env, quantity=Decimal("10"), payment_method=PaymentMethod.CREDIT, customer_id=customer.id))
    assert env["credit"].get_outstanding_balance(env["user_id"], customer.id) == Decimal("1000")


def test_one_paisa_over_the_credit_limit_is_refused(env):
    customer = make_credit_customer(env, "1000")
    with pytest.raises(ConflictError):
        env["sale"].create_sale(env["user_id"], sale_data(
            env, quantity=Decimal("10.0001"), payment_method=PaymentMethod.CREDIT,
            customer_id=customer.id))


def test_a_sale_draining_the_tank_exactly_to_zero_is_allowed(env):
    env["sale"].create_sale(env["user_id"], sale_data(env, quantity=Decimal("10000")))
    tank = env["tank"].get_tank(env["user_id"], env["tank_obj"].id)
    assert Decimal(str(tank.current_stock)) == Decimal("0")


def test_a_sale_exceeding_available_stock_is_refused_and_changes_nothing(env):
    before = Decimal(str(env["tank"].get_tank(env["user_id"], env["tank_obj"].id).current_stock))
    with pytest.raises(ConflictError):
        env["sale"].create_sale(env["user_id"], sale_data(env, quantity=Decimal("10000.001")))
    after = Decimal(str(env["tank"].get_tank(env["user_id"], env["tank_obj"].id).current_stock))
    assert after == before
    from app.models.sale import Sale
    assert env["db"].query(Sale).count() == 0, "a rejected sale left a row behind"


# =====================================================================
# Cross-module consistency
# =====================================================================

def test_a_cancelled_sale_is_excluded_from_shift_reconciliation(env):
    """If a cancellation did not reduce expected cash, every reconciliation
    after a cancellation would show a false shortage and an attendant would
    be blamed for it."""
    from app.schemas.shift_reconciliation import ShiftReconciliationPerform

    keep = env["sale"].create_sale(env["user_id"], sale_data(env, quantity=Decimal("10")))
    drop = env["sale"].create_sale(env["user_id"], sale_data(env, quantity=Decimal("5")))
    env["sale"].cancel_sale(env["user_id"], drop.id, "Voided")

    env["db"].query(Shift).filter_by(id=env["shift_id"]).update({"status": ShiftStatus.CLOSED.value})
    env["db"].commit()

    result = env["recon"].perform_shift_reconciliation(env["user_id"], ShiftReconciliationPerform(
        shift_id=env["shift_id"], declared_cash=Decimal("1000"),
        declared_upi=Decimal("0"), declared_card=Decimal("0")))

    assert Decimal(str(result.expected_cash)) == Decimal("1000"), (
        "the cancelled sale still counted toward expected cash")
    assert Decimal(str(result.cash_variance)) == Decimal("0")
    assert keep.status == SaleStatus.COMPLETED.value


def test_a_shift_cannot_be_reconciled_twice(env):
    from app.schemas.shift_reconciliation import ShiftReconciliationPerform

    env["db"].query(Shift).filter_by(id=env["shift_id"]).update({"status": ShiftStatus.CLOSED.value})
    env["db"].commit()
    data = ShiftReconciliationPerform(shift_id=env["shift_id"], declared_cash=Decimal("0"),
                                      declared_upi=Decimal("0"), declared_card=Decimal("0"))
    env["recon"].perform_shift_reconciliation(env["user_id"], data)
    with pytest.raises(ConflictError):
        env["recon"].perform_shift_reconciliation(env["user_id"], data)


def test_a_sale_cannot_be_recorded_against_a_closed_shift(env):
    env["db"].query(Shift).filter_by(id=env["shift_id"]).update({"status": ShiftStatus.CLOSED.value})
    env["db"].commit()
    with pytest.raises(ConflictError):
        env["sale"].create_sale(env["user_id"], sale_data(env))


# =====================================================================
# Local-vs-UTC date handling, the bug class this project keeps hitting
# =====================================================================

def test_customer_statement_dates_use_the_local_business_day(env):
    """A credit sale made just after local midnight belongs to the local
    day it happened on, not the UTC day. On IST (UTC+5:30) a 02:00 local
    sale is 20:30 UTC the PREVIOUS day, so using .date() on the stored
    instant dates the line a day early on a customer-facing statement."""
    customer = make_credit_customer(env)
    s = env["sale"].create_sale(env["user_id"], sale_data(
        env, quantity=Decimal("10"), payment_method=PaymentMethod.CREDIT, customer_id=customer.id))

    local_tz = datetime.now().astimezone().tzinfo
    local_moment = datetime.combine(date(2026, 6, 15), time(2, 0), tzinfo=local_tz)
    s.sale_at = local_moment
    env["db"].commit()
    env["db"].expire_all()

    statement = env["credit"].get_customer_statement(env["user_id"], customer.id)
    sale_lines = [e for e in statement if "Sale" in e.description]
    assert sale_lines, "the sale is missing from the statement"
    assert sale_lines[0].entry_date == date(2026, 6, 15), (
        f"statement dated the sale {sale_lines[0].entry_date}, "
        "but it happened on 2026-06-15 local time")


# =====================================================================
# Inputs that should never reach the database
# =====================================================================

@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1"), Decimal("-0.001")])
def test_a_sale_of_zero_or_negative_quantity_is_rejected(env, quantity):
    with pytest.raises((ValueError, ConflictError)):
        env["sale"].create_sale(env["user_id"], sale_data(env, quantity=quantity))


def test_a_credit_sale_without_a_customer_is_rejected(env):
    with pytest.raises(ValueError):
        env["sale"].create_sale(env["user_id"], sale_data(env, payment_method=PaymentMethod.CREDIT))


def test_a_credit_sale_to_a_customer_with_no_credit_account_is_rejected(env):
    """A customer record alone must not grant credit - somebody has to
    have decided a limit for them."""
    customer = env["sale"].create_customer(env["user_id"], CustomerCreate(
        name="Walk In", contact_number="9000000001"))
    with pytest.raises(ConflictError):
        env["sale"].create_sale(env["user_id"], sale_data(
            env, payment_method=PaymentMethod.CREDIT, customer_id=customer.id))


def test_cancelling_requires_a_non_blank_reason(env):
    s = env["sale"].create_sale(env["user_id"], sale_data(env))
    for blank in ("", "   ", "\t\n"):
        with pytest.raises(ValueError):
            env["sale"].cancel_sale(env["user_id"], s.id, blank)


def test_a_sale_against_an_inactive_nozzle_is_rejected(env):
    env["db"].query(Nozzle).filter_by(id=env["nozzle_id"]).update({"status": "inactive"})
    env["db"].commit()
    with pytest.raises(ConflictError):
        env["sale"].create_sale(env["user_id"], sale_data(env))


# =====================================================================
# Money precision end to end
# =====================================================================

def test_many_small_sales_sum_exactly_with_no_drift(env):
    """The reason money is Decimal: 100 sales of 0.333 litres must total
    exactly what arithmetic says, not 'about' that."""
    from app.models.sale import Sale

    for _ in range(100):
        env["sale"].create_sale(env["user_id"], sale_data(env, quantity=Decimal("0.333")))

    total = sum((Decimal(str(s.amount)) for s in env["db"].query(Sale).all()), Decimal("0"))
    # 0.333 x 100.00 = 33.30 exactly, x100 sales
    assert total == Decimal("3330.00")


def test_a_sale_amount_is_stored_settled_to_paise(env):
    """quantity (3 dp) x rate (2 dp) yields 5 dp; the stored amount must
    already be settled rather than relying on the column to truncate."""
    env["fuel"].rate_per_liter = Decimal("102.37")
    env["db"].commit()
    s = env["sale"].create_sale(env["user_id"], sale_data(env, quantity=Decimal("10.555")))
    assert Decimal(str(s.amount)) == Decimal("1080.52")  # half-up, not half-even
    assert Decimal(str(s.amount)).as_tuple().exponent == -2
