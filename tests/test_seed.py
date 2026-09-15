"""Tender seeding and the historical-data backfill (PROJECT_CONTEXT.md's
Step 1 of the settlement-side-of-daily-report build,
docs/daily-report-spec.md). Uses raw ORM inserts for Sale/Payment/
Expense rather than the real services, specifically to simulate rows
recorded *before* Tender existed - tender_id left unset, exactly the
historical shape _backfill_tender_ids has to cope with.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import PaymentMethod, TenderSettlementType
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.dispenser import Dispenser
from app.models.employee import Employee
from app.models.expense import Expense, ExpenseCategory
from app.models.fuel import Fuel
from app.models.nozzle import Nozzle
from app.models.payment import Payment
from app.models.sale import Sale
from app.models.shift import Shift
from app.models.tender import Tender
from app.models.user import User


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_seed.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


def test_seed_tenders_creates_the_eight_report_tenders(db_session):
    seed_initial_data()

    tenders = {t.name: t for t in db_session.query(Tender).all()}
    assert set(tenders) == {"Cash", "Credit", "Card", "DTP Card", "PhonePe", "Paytm", "Expenses", "Other"}
    assert tenders["Cash"].settlement_type == TenderSettlementType.IMMEDIATE_CASH.value
    assert tenders["Credit"].settlement_type == TenderSettlementType.INVOICED_CREDIT.value
    assert tenders["Card"].settlement_type == TenderSettlementType.BANK_SETTLED.value
    assert tenders["DTP Card"].settlement_type == TenderSettlementType.BANK_SETTLED.value
    for t in tenders.values():
        assert t.status == "active"


def test_seed_tenders_is_idempotent(db_session):
    seed_initial_data()
    seed_initial_data()

    assert db_session.query(Tender).count() == 8


def test_seed_tenders_corrects_a_drifted_settlement_type(db_session):
    """Regression test for a real incident, not a hypothetical: "Other"
    shipped with the wrong settlement_type for one commit (see
    DEFAULT_TENDERS's own comment in app/core/constants.py) - a database
    that had already seeded the wrong value must self-correct on the
    next startup once the code is fixed, not stay wrong forever."""
    seed_initial_data()
    other = db_session.query(Tender).filter_by(name="Other").first()
    other.settlement_type = "immediate_cash"  # simulate the old, wrong seed
    db_session.commit()

    seed_initial_data()

    db_session.refresh(other)
    assert other.settlement_type == TenderSettlementType.BANK_SETTLED.value


def _make_historical_prereqs(db_session, admin_id):
    """A minimal, valid set of parent rows so a raw Sale/Payment/Expense
    insert satisfies every foreign key - mirroring what a real service
    would have created, but built directly so tender_id can be left
    unset the way a pre-Tender row genuinely was."""
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=Decimal("100.00"))
    dispenser = Dispenser(code="D1")
    db_session.add_all([fuel, dispenser])
    db_session.commit()

    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel.id, status="active")
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add_all([nozzle, employee])
    db_session.commit()

    shift = Shift(shift_date=date(2026, 1, 1), shift_label="Morning", opened_by_id=admin_id, status="closed")
    category = ExpenseCategory(name="Diesel Exp", status="active")
    db_session.add_all([shift, category])
    db_session.commit()

    return {"fuel": fuel, "nozzle": nozzle, "employee": employee, "shift": shift, "category": category}


def test_backfill_tender_ids_maps_cash_card_credit_to_their_like_named_tender(db_session):
    seed_initial_data()  # creates the admin user + tenders needed below
    admin = db_session.query(User).filter_by(username="admin").first()
    prereqs = _make_historical_prereqs(db_session, admin.id)

    sales = {}
    for method in (PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.CREDIT):
        sale = Sale(
            receipt_number=f"R-{method.value}", shift_id=prereqs["shift"].id, nozzle_id=prereqs["nozzle"].id,
            fuel_id=prereqs["fuel"].id, employee_id=prereqs["employee"].id, quantity=Decimal("10"),
            rate_per_liter=Decimal("100.00"), amount=Decimal("1000.00"), payment_method=method.value,
            status="completed", recorded_by_id=admin.id,
        )
        db_session.add(sale)
        sales[method] = sale
    db_session.commit()
    assert all(s.tender_id is None for s in sales.values())  # historical shape, before backfill

    seed_initial_data()  # runs the backfill

    for sale in sales.values():
        db_session.refresh(sale)
    tenders_by_id = {t.id: t.name for t in db_session.query(Tender).all()}
    assert tenders_by_id[sales[PaymentMethod.CASH].tender_id] == "Cash"
    assert tenders_by_id[sales[PaymentMethod.CARD].tender_id] == "Card"
    assert tenders_by_id[sales[PaymentMethod.CREDIT].tender_id] == "Credit"


def test_backfill_tender_ids_maps_historical_upi_to_other_not_a_guessed_app(db_session):
    """PaymentMethod.UPI never recorded which app was actually used -
    the backfill must not fabricate PhonePe or Paytm. See
    PAYMENT_METHOD_TO_TENDER_NAME's own comment (app/core/constants.py)."""
    seed_initial_data()
    admin = db_session.query(User).filter_by(username="admin").first()
    prereqs = _make_historical_prereqs(db_session, admin.id)

    sale = Sale(
        receipt_number="R-UPI", shift_id=prereqs["shift"].id, nozzle_id=prereqs["nozzle"].id,
        fuel_id=prereqs["fuel"].id, employee_id=prereqs["employee"].id, quantity=Decimal("5"),
        rate_per_liter=Decimal("100.00"), amount=Decimal("500.00"), payment_method=PaymentMethod.UPI.value,
        status="completed", recorded_by_id=admin.id,
    )
    db_session.add(sale)
    db_session.commit()

    seed_initial_data()
    db_session.refresh(sale)

    tender = db_session.query(Tender).filter_by(id=sale.tender_id).first()
    assert tender.name == "Other"


def test_backfill_tender_ids_covers_payments_and_expenses_too(db_session):
    seed_initial_data()
    admin = db_session.query(User).filter_by(username="admin").first()
    prereqs = _make_historical_prereqs(db_session, admin.id)

    sale = Sale(
        receipt_number="R-PAY", shift_id=prereqs["shift"].id, nozzle_id=prereqs["nozzle"].id,
        fuel_id=prereqs["fuel"].id, employee_id=prereqs["employee"].id, quantity=Decimal("5"),
        rate_per_liter=Decimal("100.00"), amount=Decimal("500.00"), payment_method=PaymentMethod.CASH.value,
        status="completed", recorded_by_id=admin.id,
    )
    db_session.add(sale)
    db_session.commit()

    payment = Payment(
        sale_id=sale.id, amount=Decimal("500.00"), method=PaymentMethod.CASH.value, status="success",
        shift_id=prereqs["shift"].id, attendant_id=prereqs["employee"].id, recorded_by_id=admin.id,
    )
    expense = Expense(
        category_id=prereqs["category"].id, amount=Decimal("150.00"), expense_date=date(2026, 1, 1),
        payment_method=PaymentMethod.CASH.value, employee_id=prereqs["employee"].id, status="pending",
        recorded_by_id=admin.id,
    )
    db_session.add_all([payment, expense])
    db_session.commit()

    seed_initial_data()
    db_session.refresh(payment)
    db_session.refresh(expense)

    cash_tender = db_session.query(Tender).filter_by(name="Cash").first()
    assert payment.tender_id == cash_tender.id
    assert expense.tender_id == cash_tender.id
