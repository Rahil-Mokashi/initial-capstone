"""Value invariants are enforced by the DATABASE, not only by Python.

The project already went to real trouble to make foreign keys enforced at
the database level rather than in the ORM only (PRAGMA foreign_keys=ON,
installed on every connection by app/database/connection.py). Until now
every *value* rule - quantity above zero, stock within capacity, closing
meter not below opening - lived only in service code. The argument for
both is identical, and it matters here more than in a typical app because
the .db file sits on a forecourt PC and is directly reachable by anyone
with the machine and a DB browser.

These tests deliberately bypass the service layer and write straight to
the database, because that is exactly the attack the constraints defend
against. A service-layer test would prove nothing about them.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.database.connection  # noqa: F401  (installs the FK/WAL pragma listener)
import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.models.fuel import Fuel
from app.models.tank import Tank


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_checks.db'}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = factory()
    yield session
    session.close()


@pytest.fixture()
def fuel_id(db_session):
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=Decimal("100.00"))
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


@pytest.fixture()
def tank(db_session, fuel_id):
    tank = Tank(code="T1", fuel_id=fuel_id, capacity=Decimal("20000"),
                current_stock=Decimal("10000"), opening_stock=Decimal("10000"))
    db_session.add(tank)
    db_session.commit()
    return tank


def _raw_update(session, sql):
    """Straight SQL, no ORM and no service layer - the case the
    constraints exist for."""
    session.execute(text(sql))
    session.commit()


# ---------------------------------------------------------------------
# Tanks
# ---------------------------------------------------------------------

def test_tank_stock_cannot_go_negative(db_session, tank):
    with pytest.raises(IntegrityError, match="ck_tanks_stock_non_negative"):
        _raw_update(db_session, "UPDATE tanks SET current_stock = -1")


def test_tank_stock_cannot_exceed_capacity(db_session, tank):
    with pytest.raises(IntegrityError, match="ck_tanks_stock_within_capacity"):
        _raw_update(db_session, "UPDATE tanks SET current_stock = 999999")


def test_tank_capacity_must_be_positive(db_session, fuel_id):
    with pytest.raises(IntegrityError, match="ck_tanks_capacity_positive"):
        db_session.add(Tank(code="T2", fuel_id=fuel_id, capacity=Decimal("0"),
                            current_stock=Decimal("0"), opening_stock=Decimal("0")))
        db_session.commit()


def test_a_legitimate_stock_change_is_still_allowed(db_session, tank):
    """The guard against over-constraining: normal operation must work."""
    _raw_update(db_session, "UPDATE tanks SET current_stock = 15000")
    db_session.expire_all()
    assert Decimal(str(db_session.query(Tank).first().current_stock)) == Decimal("15000")


# ---------------------------------------------------------------------
# Fuel prices
# ---------------------------------------------------------------------

def test_a_fuel_rate_cannot_be_negative(db_session, fuel_id):
    # fuel_id is required, not decorative: without a row to update, the
    # UPDATE touches nothing and passes the constraint vacuously.
    with pytest.raises(IntegrityError, match="ck_fuels_rate_non_negative"):
        _raw_update(db_session, "UPDATE fuels SET rate_per_liter = -10")


def test_the_seeded_zero_rate_is_still_permitted(db_session, fuel_id):
    """0.00 means 'not priced yet' and must remain storable - the guard
    against it is at the service layer (a sale is refused), deliberately
    not here, because seeding legitimately writes it."""
    _raw_update(db_session, "UPDATE fuels SET rate_per_liter = 0")
    db_session.expire_all()
    assert Decimal(str(db_session.query(Fuel).first().rate_per_liter)) == Decimal("0")


# ---------------------------------------------------------------------
# The constraints exist on the tables the migration targeted
# ---------------------------------------------------------------------

EXPECTED = {
    "tanks": ["ck_tanks_capacity_positive", "ck_tanks_stock_non_negative",
              "ck_tanks_stock_within_capacity"],
    "sales": ["ck_sales_quantity_positive", "ck_sales_rate_non_negative",
              "ck_sales_amount_non_negative"],
    "tank_transactions": ["ck_tank_transactions_quantity_non_zero"],
    "nozzle_assignments": ["ck_nozzle_assignments_opening_meter_non_negative",
                           "ck_nozzle_assignments_closing_not_before_opening"],
    "payments": ["ck_payments_amount_non_negative"],
    "expenses": ["ck_expenses_amount_positive"],
    "credit_accounts": ["ck_credit_accounts_limit_non_negative",
                        "ck_credit_accounts_due_days_non_negative"],
    "fuels": ["ck_fuels_rate_non_negative"],
    "fuel_price_history": ["ck_fuel_price_history_new_rate_positive"],
}


@pytest.mark.parametrize("table, constraints", sorted(EXPECTED.items()))
def test_expected_constraints_are_present_in_the_schema(db_session, table, constraints):
    ddl = db_session.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=:t"
    ), {"t": table}).scalar()
    assert ddl, f"table {table} does not exist"
    for name in constraints:
        assert name in ddl, f"{name} missing from {table}"


def test_the_expenses_constraint_is_on_expenses_not_expense_categories(db_session):
    """Regression: expense.py defines two models, and the constraint was
    initially attached to the first __tablename__ in the file
    (expense_categories, which has no amount column at all)."""
    categories_ddl = db_session.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='expense_categories'"
    )).scalar()
    assert "ck_expenses_amount_positive" not in (categories_ddl or "")


def test_a_completed_assignment_may_have_an_equal_closing_meter(db_session):
    """closing_meter >= opening_meter, not strictly greater: a nozzle that
    dispensed nothing during a shift is normal, not a data error."""
    ddl = db_session.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='nozzle_assignments'"
    )).scalar()
    assert "closing_meter >= opening_meter" in ddl
    assert "closing_meter IS NULL" in ddl, "an in-progress assignment must still be storable"


def test_tank_transaction_quantity_is_signed_not_positive(db_session):
    """Regression on a constraint I got wrong first time.

    TankTransaction.quantity is a SIGNED stock delta:
    TankService._record_transaction stores an ISSUE as negative, a RECEIPT
    as positive, and an ADJUSTMENT with whichever sign corrects the tank.
    A "quantity > 0" constraint therefore contradicts the domain model
    rather than protecting it, and broke 53 tests.

    It also slipped past a pre-flight check against the demo database,
    because scripts/seed_demo_data.py inserts bulk history directly rather
    than through the service layer - so the demo data contained no negative
    quantities and was not representative of the real code path. Validating
    a constraint against data that never exercised the code it constrains
    proves nothing.
    """
    ddl = db_session.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tank_transactions'"
    )).scalar()
    assert "quantity != 0" in ddl
    assert "quantity > 0" not in ddl, "a positivity constraint would reject every ISSUE"
