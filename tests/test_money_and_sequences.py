"""Money rounding and document-number sequences.

Two things that look trivial, are not, and had no test pinning them
before: which way a half-paisa rounds, and what happens to the receipt
sequence after a restore from backup.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.money import money, volume
from app.database.base import Base
from app.models.employee import Employee
from app.models.sale import Sale
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.sale_repository import SaleRepository


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_money.db'}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = factory()
    yield session
    session.close()


# ---------------------------------------------------------------------
# Money rounding
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        # The cases that separate ROUND_HALF_UP from Python's default
        # ROUND_HALF_EVEN. Under banker's rounding 0.125 -> 0.12 and
        # 2.675 -> 2.68; Indian invoicing expects both to round up.
        ("0.125", "0.13"),
        ("0.135", "0.14"),
        ("2.345", "2.35"),
        ("1.005", "1.01"),
        # Ordinary cases, unaffected by the mode.
        ("10.004", "10.00"),
        ("10.006", "10.01"),
        ("99.999", "100.00"),
        ("0", "0.00"),
    ],
)
def test_money_rounds_half_up_to_paise(raw, expected):
    assert money(Decimal(raw)) == Decimal(expected)


def test_money_never_routes_a_float_through_binary_representation():
    """Decimal(0.1) preserves the float's error; Decimal("0.1") does not.
    money() must take the second path or exactness is lost at the door."""
    assert money(0.1) == Decimal("0.10")
    assert money(2.675) == Decimal("2.68")  # Decimal(2.675) would give 2.67


def test_money_is_exact_across_repeated_addition():
    """The whole reason money is Decimal and not float: 0.1 + 0.2 != 0.3
    in binary floating point, and the error compounds over a day of sales."""
    total = sum((money("0.10") for _ in range(10)), Decimal("0"))
    assert total == Decimal("1.00")


def test_volume_settles_to_millilitres():
    assert volume(Decimal("12.3456")) == Decimal("12.346")
    assert volume(Decimal("12.3454")) == Decimal("12.345")


def test_a_sale_amount_is_settled_to_paise():
    """quantity (3 dp) x rate (2 dp) produces 5 dp; the stored amount must
    already be a settled 2 dp figure rather than relying on the column."""
    assert money(Decimal("10.555") * Decimal("102.37")) == Decimal("1080.52")


# ---------------------------------------------------------------------
# Document sequences
# ---------------------------------------------------------------------

def _add_sale(session, receipt_number):
    session.add(Sale(
        receipt_number=receipt_number, shift_id="s", nozzle_id="n", fuel_id="f",
        employee_id="e", quantity=Decimal("1"), rate_per_liter=Decimal("1"),
        amount=Decimal("1"), payment_method="cash", status="completed",
        recorded_by_id="u",
    ))
    session.commit()


def test_receipt_numbers_start_at_one_and_increment(db_session):
    repo = SaleRepository(db_session)
    assert repo.next_receipt_number() == "RCPT-000001"
    _add_sale(db_session, "RCPT-000001")
    assert repo.next_receipt_number() == "RCPT-000002"
    _add_sale(db_session, "RCPT-000002")
    assert repo.next_receipt_number() == "RCPT-000003"


def test_receipt_number_survives_a_gap_in_the_sequence(db_session):
    """The regression this fix exists for.

    A restore from backup (or any row disappearing) makes the row count
    disagree with the highest number actually issued. The old COUNT(*) + 1
    then returned a number that already existed, the unique index rejected
    the insert, and every further sale was blocked.
    """
    repo = SaleRepository(db_session)
    for n in (1, 2, 3, 4, 5):
        _add_sale(db_session, f"RCPT-{n:06d}")

    # Simulate the post-restore state: fewer rows than numbers issued.
    db_session.query(Sale).filter(Sale.receipt_number.in_(["RCPT-000002", "RCPT-000003"])).delete(
        synchronize_session=False
    )
    db_session.commit()

    assert db_session.query(Sale).count() == 3
    # COUNT(*) + 1 would say RCPT-000004, which already exists.
    assert repo.next_receipt_number() == "RCPT-000006"


def test_receipt_number_falls_back_rather_than_wedging_on_a_malformed_row(db_session):
    """A hand-edited or legacy receipt number must not block all sales."""
    repo = SaleRepository(db_session)
    _add_sale(db_session, "LEGACY")
    assert repo.next_receipt_number().startswith("RCPT-")


def test_employee_codes_survive_a_gap_too(db_session):
    repo = EmployeeRepository(db_session)
    for n in (1, 2, 3):
        db_session.add(Employee(
            employee_code=f"EMP-{n:04d}", first_name="A", last_name="B",
            contact_number="9000000000", joining_date=date(2026, 1, 1),
        ))
    db_session.commit()

    db_session.query(Employee).filter_by(employee_code="EMP-0002").delete(synchronize_session=False)
    db_session.commit()

    assert repo.next_employee_code() == "EMP-0004"
