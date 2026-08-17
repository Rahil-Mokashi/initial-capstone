"""Fuel selling prices and their history.

Closes the app's single largest functional gap: fuels seeded at 0.00 with
nothing in the application able to change them, so every sale on a fresh
install booked zero revenue.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, ShiftStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
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
from app.repositories.fuel_price_history_repository import FuelPriceHistoryRepository
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
from app.schemas.fuel import FuelCreate, FuelRateChange
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.fuel_service import FuelService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_fuel.db'}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", factory)
    session = factory()
    yield session
    session.close()


def make_user(db_session, role_name, username):
    role = db_session.query(Role).filter_by(name=role_name).first()
    user = User(
        username=username, email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"), role=role, is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


@pytest.fixture()
def manager_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.MANAGER.value, "manager1")


@pytest.fixture()
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1")


@pytest.fixture()
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1")


@pytest.fixture()
def fuel_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return FuelService(
        FuelRepository(db_session), FuelPriceHistoryRepository(db_session), audit_repo, auth
    )


def petrol(db_session):
    return db_session.query(Fuel).filter_by(fuel_type="Petrol").first()


# ---------------------------------------------------------------------
# The gap this module closes
# ---------------------------------------------------------------------

def test_seeded_fuels_start_unpriced(db_session, manager_id, fuel_service):
    """Documents the state the app shipped in: every fuel at 0.00."""
    unpriced = fuel_service.list_unpriced_fuels(manager_id)
    assert {f.fuel_type for f in unpriced} == {"Petrol", "Diesel", "Power"}


def test_a_manager_can_set_a_price(db_session, manager_id, fuel_service):
    fuel = fuel_service.set_rate(
        manager_id, petrol(db_session).id,
        FuelRateChange(new_rate_per_liter=Decimal("104.75"), reason="Daily OMC revision"),
    )
    assert Decimal(str(fuel.rate_per_liter)) == Decimal("104.75")
    assert fuel_service.list_unpriced_fuels(manager_id) != []  # Diesel/Power still unpriced
    assert "Petrol" not in {f.fuel_type for f in fuel_service.list_unpriced_fuels(manager_id)}


def test_price_change_is_recorded_in_history_with_who_and_why(db_session, manager_id, fuel_service):
    fuel_id = petrol(db_session).id
    fuel_service.set_rate(manager_id, fuel_id, FuelRateChange(
        new_rate_per_liter=Decimal("100.00"), reason="Opening price"))
    fuel_service.set_rate(manager_id, fuel_id, FuelRateChange(
        new_rate_per_liter=Decimal("102.50"), reason="OMC increase"))

    history = fuel_service.get_price_history(manager_id, fuel_id)
    assert len(history) == 2
    latest, first = history[0], history[1]

    assert Decimal(str(latest.new_rate_per_liter)) == Decimal("102.50")
    assert Decimal(str(latest.old_rate_per_liter)) == Decimal("100.00")
    assert latest.reason == "OMC increase"
    assert latest.changed_by_id == manager_id

    # The seeded 0.00 is a placeholder, not a price anyone set, so the
    # first real price has no predecessor rather than claiming one.
    assert first.old_rate_per_liter is None


def test_price_change_is_audit_logged(db_session, manager_id, fuel_service):
    fuel_service.set_rate(manager_id, petrol(db_session).id, FuelRateChange(
        new_rate_per_liter=Decimal("99.99"), reason="Correction"))
    events = db_session.query(AuditLog).filter_by(event_type="fuel_price_changed").all()
    assert len(events) == 1
    assert "99.99" in events[0].description


def test_price_is_settled_to_paise(db_session, manager_id, fuel_service):
    fuel = fuel_service.set_rate(manager_id, petrol(db_session).id, FuelRateChange(
        new_rate_per_liter=Decimal("100.125"), reason="Rounding check"))
    assert Decimal(str(fuel.rate_per_liter)) == Decimal("100.13")  # half-up, not half-even


# ---------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------

def test_setting_the_same_price_again_is_rejected(db_session, manager_id, fuel_service):
    fuel_id = petrol(db_session).id
    fuel_service.set_rate(manager_id, fuel_id, FuelRateChange(
        new_rate_per_liter=Decimal("100.00"), reason="Opening price"))
    with pytest.raises(ConflictError):
        fuel_service.set_rate(manager_id, fuel_id, FuelRateChange(
            new_rate_per_liter=Decimal("100.00"), reason="Same again"))
    assert len(fuel_service.get_price_history(manager_id, fuel_id)) == 1


def test_a_reason_is_required():
    with pytest.raises(ValueError):
        FuelRateChange(new_rate_per_liter=Decimal("100"), reason="   ")


@pytest.mark.parametrize("rate", [Decimal("0"), Decimal("-5"), Decimal("100000")])
def test_implausible_rates_are_rejected_at_the_boundary(rate):
    with pytest.raises(ValueError):
        FuelRateChange(new_rate_per_liter=rate, reason="Typo")


def test_accountant_can_view_but_not_change(db_session, accountant_id, fuel_service):
    fuel_service.list_fuels(accountant_id)  # allowed
    with pytest.raises(PermissionDeniedError):
        fuel_service.set_rate(accountant_id, petrol(db_session).id, FuelRateChange(
            new_rate_per_liter=Decimal("100"), reason="Not allowed"))


def test_attendant_can_see_prices_but_not_change_them(db_session, attendant_id, fuel_service):
    fuel_service.list_fuels(attendant_id)  # an attendant quotes the price to the customer
    with pytest.raises(PermissionDeniedError):
        fuel_service.set_rate(attendant_id, petrol(db_session).id, FuelRateChange(
            new_rate_per_liter=Decimal("100"), reason="Not allowed"))


def test_unknown_fuel_raises_not_found(db_session, manager_id, fuel_service):
    with pytest.raises(NotFoundError):
        fuel_service.set_rate(manager_id, "no-such-fuel", FuelRateChange(
            new_rate_per_liter=Decimal("100"), reason="x"))


def test_create_fuel_records_its_opening_price(db_session, manager_id, fuel_service):
    fuel = fuel_service.create_fuel(manager_id, FuelCreate(
        fuel_type="CNG", rate_per_liter=Decimal("76.50")))
    history = fuel_service.get_price_history(manager_id, fuel.id)
    assert len(history) == 1
    assert history[0].old_rate_per_liter is None
    assert Decimal(str(history[0].new_rate_per_liter)) == Decimal("76.50")


def test_duplicate_fuel_type_is_rejected(db_session, manager_id, fuel_service):
    with pytest.raises(ConflictError):
        fuel_service.create_fuel(manager_id, FuelCreate(fuel_type="petrol"))


# ---------------------------------------------------------------------
# The sale-side guard
# ---------------------------------------------------------------------

@pytest.fixture()
def sale_setup(db_session, manager_id):
    audit_repo = AuditLogRepository(db_session)
    auth = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    tank_service = TankService(
        TankRepository(db_session), TankReadingRepository(db_session),
        TankTransactionRepository(db_session), FuelReconciliationRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), audit_repo, auth,
    )
    credit_service = CreditService(
        CreditAccountRepository(db_session), CustomerPaymentRepository(db_session),
        CustomerRepository(db_session), SaleRepository(db_session), audit_repo, auth,
    )
    sale_service = SaleService(
        SaleRepository(db_session), ShiftRepository(db_session), NozzleRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), CustomerRepository(db_session),
        TankRepository(db_session), tank_service, audit_repo, auth,
        PaymentRepository(db_session), credit_service,
    )

    fuel = petrol(db_session)
    tank = tank_service.create_tank(manager_id, TankCreate(
        code="T1", fuel_id=fuel.id, capacity=20000.0, opening_stock=10000.0))
    dispenser = Dispenser(code="D1", status="active")
    db_session.add(dispenser)
    db_session.commit()
    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel.id,
                    tank_id=tank.id, status="active")
    employee = Employee(employee_code="EMP-0001", first_name="Ravi", last_name="K",
                        contact_number="9876543210", joining_date=date(2026, 1, 1))
    shift = Shift(shift_date=date.today(), shift_label="Morning",
                  opened_by_id=manager_id, status=ShiftStatus.OPEN.value)
    db_session.add_all([nozzle, employee, shift])
    db_session.commit()
    return sale_service, nozzle.id, employee.id, shift.id


def test_a_sale_of_an_unpriced_fuel_is_refused_not_booked_at_zero(
    db_session, manager_id, sale_setup
):
    """The behaviour the whole feature exists to prevent.

    Before this, the sale succeeded and recorded amount = 0.00: fuel left
    the tank, the sale looked completed and correct, and revenue was
    silently understated everywhere downstream.
    """
    sale_service, nozzle_id, employee_id, shift_id = sale_setup
    with pytest.raises(ConflictError, match="no selling price"):
        sale_service.create_sale(manager_id, SaleCreate(
            shift_id=shift_id, nozzle_id=nozzle_id, employee_id=employee_id,
            quantity=Decimal("10"), payment_method=PaymentMethod.CASH))

    from app.models.sale import Sale
    assert db_session.query(Sale).count() == 0


def test_the_same_sale_succeeds_once_a_price_is_set(
    db_session, manager_id, fuel_service, sale_setup
):
    sale_service, nozzle_id, employee_id, shift_id = sale_setup
    fuel_service.set_rate(manager_id, petrol(db_session).id, FuelRateChange(
        new_rate_per_liter=Decimal("102.40"), reason="Opening price"))

    sale = sale_service.create_sale(manager_id, SaleCreate(
        shift_id=shift_id, nozzle_id=nozzle_id, employee_id=employee_id,
        quantity=Decimal("10"), payment_method=PaymentMethod.CASH))

    assert Decimal(str(sale.amount)) == Decimal("1024.00")
    assert Decimal(str(sale.rate_per_liter)) == Decimal("102.40")


def test_a_later_price_change_does_not_alter_an_existing_sale(
    db_session, manager_id, fuel_service, sale_setup
):
    """Sale.rate_per_liter is snapshotted, per the user's confirmed
    requirement - the whole reason price history is a separate table."""
    sale_service, nozzle_id, employee_id, shift_id = sale_setup
    fuel_id = petrol(db_session).id
    fuel_service.set_rate(manager_id, fuel_id, FuelRateChange(
        new_rate_per_liter=Decimal("100.00"), reason="Opening"))
    sale = sale_service.create_sale(manager_id, SaleCreate(
        shift_id=shift_id, nozzle_id=nozzle_id, employee_id=employee_id,
        quantity=Decimal("10"), payment_method=PaymentMethod.CASH))

    fuel_service.set_rate(manager_id, fuel_id, FuelRateChange(
        new_rate_per_liter=Decimal("110.00"), reason="Hike"))

    db_session.expire_all()
    refreshed = sale_service.get_sale(manager_id, sale.id)
    assert Decimal(str(refreshed.rate_per_liter)) == Decimal("100.00")
    assert Decimal(str(refreshed.amount)) == Decimal("1000.00")
