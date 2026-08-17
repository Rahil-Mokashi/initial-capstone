"""Proves that a multi-step financial operation is all-or-nothing.

CLAUDE.md: "Always use transactions for financial operations" and
"Never allow partial financial writes."

Every other test in this suite exercises the *happy* path of a service
method, so they all passed while create_sale was really four or five
separate transactions (the Sale row, the tank ISSUE transaction plus the
tank's stock decrement, the Sale's update with the transaction id, then
the Payment row). Nothing asserted what the database looks like when a
step *after* the first one fails — which is precisely the case that left
fuel gone from a tank with no sale accounting for it, or a completed sale
with no payment record silently corrupting shift reconciliation.

These tests force a failure partway through and assert that none of the
earlier writes survived.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, ShiftStatus, TankTransactionType, UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.payment import Payment
from app.models.role import Role
from app.models.sale import Sale
from app.models.shift import Shift
from app.models.tank_transaction import TankTransaction
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
from app.repositories.base import unit_of_work
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_atomicity.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def admin_id(db_session):
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def attendant_id(db_session):
    seed_initial_data()
    role = db_session.query(Role).filter_by(name=UserRole.ATTENDANT.value).first()
    user = User(
        username="attendant1", email="attendant1@example.com",
        password_hash=hash_password("Passw0rd!"), role=role, is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


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
def services(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    tank_service = TankService(
        TankRepository(db_session), TankReadingRepository(db_session), TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session), FuelRepository(db_session), EmployeeRepository(db_session),
        audit_repo, auth_service,
    )
    credit_service = CreditService(
        CreditAccountRepository(db_session), CustomerPaymentRepository(db_session),
        CustomerRepository(db_session), SaleRepository(db_session), audit_repo, auth_service,
    )
    payment_repo = PaymentRepository(db_session)
    sale_service = SaleService(
        SaleRepository(db_session), ShiftRepository(db_session), NozzleRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), CustomerRepository(db_session),
        TankRepository(db_session), tank_service, audit_repo, auth_service, payment_repo,
        credit_service,
    )
    return sale_service, tank_service, payment_repo


@pytest.fixture()
def tank_id(services, admin_id, fuel_id):
    _, tank_service, _ = services
    tank = tank_service.create_tank(
        admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=20000.0, opening_stock=10000.0)
    )
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
    shift = Shift(
        shift_date=date.today(), shift_label="Morning",
        opened_by_id=admin_id, status=ShiftStatus.OPEN.value,
    )
    db_session.add(shift)
    db_session.commit()
    return shift.id


class _InjectedFailure(RuntimeError):
    """Stands in for any late failure: a constraint violation, a disk-full,
    a bug. What matters is only that it happens *after* earlier writes."""


def test_failed_payment_write_leaves_no_sale_no_tank_transaction_and_no_stock_change(
    db_session, services, attendant_id, employee_id, nozzle_id, tank_id, open_shift_id
):
    """The core atomicity guarantee, on the app's most important operation."""
    sale_service, tank_service, payment_repo = services

    tank_before = tank_service._tank_repo.get_by_id(tank_id)
    stock_before = Decimal(str(tank_before.current_stock))

    # Fail at the last step of create_sale, once the Sale row and the tank
    # ISSUE transaction have already been written.
    def boom(_payment):
        raise _InjectedFailure("payment write failed")

    payment_repo.add = boom

    with pytest.raises(_InjectedFailure):
        sale_service.create_sale(
            attendant_id,
            SaleCreate(
                shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id,
                quantity=Decimal("10"), payment_method=PaymentMethod.CASH,
            ),
        )

    db_session.expire_all()

    assert db_session.query(Sale).count() == 0, "a Sale survived a failed sale operation"
    assert db_session.query(Payment).count() == 0, "a Payment survived a failed sale operation"
    issues = db_session.query(TankTransaction).filter_by(
        transaction_type=TankTransactionType.ISSUE.value
    ).all()
    assert issues == [], "fuel was issued from the tank with no sale accounting for it"

    tank_after = tank_service._tank_repo.get_by_id(tank_id)
    assert Decimal(str(tank_after.current_stock)) == stock_before, "tank stock changed despite the sale failing"


def test_a_successful_sale_still_commits_everything(
    db_session, services, attendant_id, employee_id, nozzle_id, tank_id, open_shift_id
):
    """The guard against over-correcting: wrapping the operation in one
    transaction must not stop it committing when nothing goes wrong."""
    sale_service, tank_service, _ = services

    sale = sale_service.create_sale(
        attendant_id,
        SaleCreate(
            shift_id=open_shift_id, nozzle_id=nozzle_id, employee_id=employee_id,
            quantity=Decimal("10"), payment_method=PaymentMethod.CASH,
        ),
    )

    db_session.expire_all()

    assert db_session.query(Sale).count() == 1
    assert db_session.query(Payment).filter_by(sale_id=sale.id).count() == 1
    assert db_session.query(TankTransaction).filter_by(
        transaction_type=TankTransactionType.ISSUE.value
    ).count() == 1
    tank = tank_service._tank_repo.get_by_id(tank_id)
    assert Decimal(str(tank.current_stock)) == Decimal("9990")


def test_unit_of_work_nests_without_the_inner_block_committing_early(db_session, admin_id):
    """A service calling another service must not have its atomicity broken
    by the inner one committing. Only the outermost block commits.

    Note the deliberately unusual fuel names: seed_initial_data() already
    creates Petrol, Diesel and Power, so asserting on those would test the
    seeder rather than the rollback.
    """
    with pytest.raises(_InjectedFailure):
        with unit_of_work(db_session):
            db_session.add(Fuel(fuel_type="OuterBlockFuel", rate_per_liter=Decimal("90.00")))
            db_session.flush()

            with unit_of_work(db_session):  # inner service's own boundary
                db_session.add(Fuel(fuel_type="InnerBlockFuel", rate_per_liter=Decimal("110.00")))
                db_session.flush()

            raise _InjectedFailure("outer step failed after the inner one finished")

    db_session.expire_all()
    remaining = {f.fuel_type for f in db_session.query(Fuel).all()}
    assert "OuterBlockFuel" not in remaining, "the outer block's write survived a rollback"
    assert "InnerBlockFuel" not in remaining, "the inner block committed early and escaped the outer rollback"
