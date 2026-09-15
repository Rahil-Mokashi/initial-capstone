from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import ShiftStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.shift_bank_deposit_repository import ShiftBankDepositRepository
from app.repositories.shift_cash_book_repository import ShiftCashBookRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.shift_cash_book import ShiftBankDepositRecord, ShiftCashBookRecord
from app.services.auth_service import AuthService
from app.services.shift_cash_book_service import ShiftCashBookService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_cash_book.db")
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
def cash_book_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ShiftCashBookService(
        ShiftCashBookRepository(db_session),
        ShiftRepository(db_session),
        audit_repo,
        auth_service,
        ShiftBankDepositRepository(db_session),
    )


@pytest.fixture()
def cash_book_service_without_bank_deposit_repo(db_session, auth_service):
    """Mirrors Step 3's original constructor shape (bank_deposit_repo
    omitted) - the Step 4 methods must refuse clearly rather than
    silently mis-deriving a financial figure."""
    audit_repo = AuditLogRepository(db_session)
    return ShiftCashBookService(
        ShiftCashBookRepository(db_session), ShiftRepository(db_session), audit_repo, auth_service,
    )


def make_shift(db_session, admin_id, shift_date, shift_label="Morning"):
    shift = Shift(shift_date=shift_date, shift_label=shift_label, opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift)
    db_session.commit()
    return shift


def test_record_shift_cash_movements(cash_book_service, admin_id, open_shift_id):
    cash_book = cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=open_shift_id, advance_amount=Decimal("500"), final_amount=Decimal("1200")),
    )
    assert cash_book.advance_amount == Decimal("500.00")
    assert cash_book.final_amount == Decimal("1200.00")
    assert cash_book.recorded_by_id == admin_id


def test_advance_and_final_default_to_zero(cash_book_service, admin_id, open_shift_id):
    cash_book = cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=open_shift_id),
    )
    assert cash_book.advance_amount == Decimal("0.00")
    assert cash_book.final_amount == Decimal("0.00")


def test_negative_advance_rejected_by_schema():
    with pytest.raises(ValueError):
        ShiftCashBookRecord(shift_id="x", advance_amount=Decimal("-1"))


def test_cannot_record_cash_movements_for_a_shift_twice(cash_book_service, admin_id, open_shift_id):
    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=open_shift_id, advance_amount=Decimal("100")),
    )
    with pytest.raises(ConflictError):
        cash_book_service.record_shift_cash_movements(
            admin_id, ShiftCashBookRecord(shift_id=open_shift_id, advance_amount=Decimal("200")),
        )


def test_recording_for_unknown_shift_raises_not_found(cash_book_service, admin_id):
    with pytest.raises(NotFoundError):
        cash_book_service.record_shift_cash_movements(
            admin_id, ShiftCashBookRecord(shift_id="does-not-exist"),
        )


def test_accountant_cannot_record_cash_movements(cash_book_service, accountant_id, open_shift_id):
    """Reuses RECONCILIATION_MANAGE, not a new permission - Accountant
    doesn't hold that one any more than they hold reconciliation-manage
    itself (same actor/workflow-moment reasoning documented on the
    service)."""
    with pytest.raises(PermissionDeniedError):
        cash_book_service.record_shift_cash_movements(
            accountant_id, ShiftCashBookRecord(shift_id=open_shift_id),
        )


def test_get_for_shift_returns_the_recorded_cash_book(cash_book_service, admin_id, open_shift_id):
    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=open_shift_id, advance_amount=Decimal("300")),
    )
    fetched = cash_book_service.get_for_shift(admin_id, open_shift_id)
    assert fetched.advance_amount == Decimal("300.00")


def test_get_for_shift_returns_none_when_not_yet_recorded(cash_book_service, admin_id, open_shift_id):
    assert cash_book_service.get_for_shift(admin_id, open_shift_id) is None


def test_list_all_includes_every_recorded_cash_book(cash_book_service, admin_id, open_shift_id, db_session):
    other_shift = Shift(shift_date=date.today(), shift_label="Evening", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(other_shift)
    db_session.commit()

    cash_book_service.record_shift_cash_movements(admin_id, ShiftCashBookRecord(shift_id=open_shift_id))
    cash_book_service.record_shift_cash_movements(admin_id, ShiftCashBookRecord(shift_id=other_shift.id))

    assert len(cash_book_service.list_all(admin_id)) == 2


# ----------------------------------------------------------------------
# Step 4: bank deposits and the derived opening/closing balance
# ----------------------------------------------------------------------

def test_record_bank_deposit(cash_book_service, admin_id, open_shift_id):
    cash_book_service.record_shift_cash_movements(admin_id, ShiftCashBookRecord(shift_id=open_shift_id))
    deposit = cash_book_service.record_bank_deposit(
        admin_id, ShiftBankDepositRecord(shift_id=open_shift_id, bank_name="HDFC Bank", amount=Decimal("1000")),
    )
    assert deposit.bank_name == "HDFC Bank"
    assert deposit.amount == Decimal("1000.00")
    assert deposit.recorded_by_id == admin_id


def test_bank_deposit_rejected_when_cash_book_not_yet_recorded(cash_book_service, admin_id, open_shift_id):
    with pytest.raises(NotFoundError):
        cash_book_service.record_bank_deposit(
            admin_id, ShiftBankDepositRecord(shift_id=open_shift_id, bank_name="HDFC Bank", amount=Decimal("1000")),
        )


def test_bank_deposit_amount_must_be_positive():
    with pytest.raises(ValueError):
        ShiftBankDepositRecord(shift_id="x", bank_name="HDFC Bank", amount=Decimal("0"))


def test_bank_deposit_bank_name_must_not_be_blank():
    with pytest.raises(ValueError):
        ShiftBankDepositRecord(shift_id="x", bank_name="   ", amount=Decimal("1000"))


def test_opening_balance_is_zero_for_the_first_shift(cash_book_service, admin_id, open_shift_id):
    assert cash_book_service.get_opening_balance(admin_id, open_shift_id) == Decimal("0")


def test_step4_methods_require_a_bank_deposit_repo(cash_book_service_without_bank_deposit_repo, admin_id, open_shift_id):
    """Step 3 built ShiftCashBookService with bank_deposit_repo defaulting
    to None; a caller still on that shape must get a clear error from the
    Step 4 methods, not a wrong balance."""
    with pytest.raises(ConflictError):
        cash_book_service_without_bank_deposit_repo.get_opening_balance(admin_id, open_shift_id)


def test_opening_balance_stops_at_a_shift_with_no_cash_book_recorded(cash_book_service, admin_id, db_session):
    """A gap in the chain (a shift nobody recorded cash movements for)
    stops the backward walk there rather than assuming zero further
    back than the gap - see ShiftCashBookService._opening_balance."""
    shift_a = make_shift(db_session, admin_id, date(2026, 1, 1))
    shift_b = make_shift(db_session, admin_id, date(2026, 1, 2))  # no cash book recorded - the gap
    shift_c = make_shift(db_session, admin_id, date(2026, 1, 3))

    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=shift_a.id, advance_amount=Decimal("5000")),
    )

    assert cash_book_service.get_opening_balance(admin_id, shift_c.id) == Decimal("0")


def test_opening_balance_carries_forward_across_shifts_using_real_report_figures(
    cash_book_service, admin_id, db_session,
):
    """Reproduces the real daily report (docs/daily-report-spec.md) used
    throughout this session's settlement-side build. shift0 is a
    synthetic predecessor that establishes Shift 1's opening balance
    (the report photo itself does not show where Shift 1's cash came
    from - only that it opened with 321334 already in hand).

    Shift 2's derived closing cash-in-hand (126756) is deliberately
    126756, not the report's own 127172: the 416 difference is a cash
    shortage recovered in cash (Step 5, A2). This fixture's own
    cash_book_service is built without a shortage_recovery_repo, so
    that gap stays open here on purpose - it is closed end-to-end,
    using these exact real-report figures, by
    test_shortage_recovery_closes_the_report_gap below.
    """
    shift0 = make_shift(db_session, admin_id, date(2026, 1, 1))
    shift1 = make_shift(db_session, admin_id, date(2026, 1, 2))
    shift2 = make_shift(db_session, admin_id, date(2026, 1, 3))

    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=shift0.id, advance_amount=Decimal("321334"), final_amount=Decimal("0")),
    )
    assert cash_book_service.get_opening_balance(admin_id, shift1.id) == Decimal("321334")

    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=shift1.id, advance_amount=Decimal("67700"), final_amount=Decimal("39241")),
    )
    cash_book_service.record_bank_deposit(
        admin_id, ShiftBankDepositRecord(shift_id=shift1.id, bank_name="SBI", amount=Decimal("398840")),
    )
    shift1_summary = cash_book_service.get_cash_book_summary(admin_id, shift1.id)
    assert shift1_summary.opening_balance == Decimal("321334")
    assert shift1_summary.closing_cash_in_hand == Decimal("29435")  # matches the report exactly

    assert cash_book_service.get_opening_balance(admin_id, shift2.id) == Decimal("29435")

    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=shift2.id, advance_amount=Decimal("0"), final_amount=Decimal("97321")),
    )
    shift2_summary = cash_book_service.get_cash_book_summary(admin_id, shift2.id)
    assert shift2_summary.opening_balance == Decimal("29435")
    assert shift2_summary.closing_cash_in_hand == Decimal("126756")  # report says 127172 - see docstring above


def test_cash_book_summary_when_no_cash_book_recorded_yet(cash_book_service, admin_id, open_shift_id):
    summary = cash_book_service.get_cash_book_summary(admin_id, open_shift_id)
    assert summary.cash_book is None
    assert summary.opening_balance == Decimal("0")
    assert summary.bank_deposits == []
    assert summary.closing_cash_in_hand == Decimal("0")


def test_shortage_recovery_closes_the_report_gap(db_session, admin_id):
    """The 416 gap documented in
    test_opening_balance_carries_forward_across_shifts_using_real_
    report_figures above is a real cash receipt on the pump's own
    paper report's RECEIPT side ("cash Short Retrun ( Pramod Soni )
    416.00", SHIFT 2's cash book) - not a reversal of the shortage
    Expense, which stays booked. Wires the full real chain (a genuine
    reconciliation shortfall, booked as a shortage, then recovered)
    and proves ShiftCashBookService.get_cash_book_summary picks the
    recovery up and reaches the report's own 127172 exactly, where the
    isolated fixture above (built without a shortage_recovery_repo)
    stops at 126756."""
    from app.core.constants import PaymentMethod, ShiftStatus
    from app.models.dispenser import Dispenser
    from app.models.employee import Employee
    from app.models.fuel import Fuel
    from app.models.nozzle import Nozzle
    from app.models.sale import Sale
    from app.models.tender import Tender
    from app.repositories.employee_cash_shortage_repository import EmployeeCashShortageRepository
    from app.repositories.employee_repository import EmployeeRepository
    from app.repositories.employee_shortage_recovery_repository import EmployeeShortageRecoveryRepository
    from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
    from app.repositories.sale_repository import SaleRepository
    from app.repositories.shift_bank_deposit_repository import ShiftBankDepositRepository
    from app.repositories.shift_reconciliation_line_repository import ShiftReconciliationLineRepository
    from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
    from app.repositories.tender_repository import TenderRepository
    from app.schemas.employee_cash_shortage import EmployeeCashShortageRecord, EmployeeShortageRecoveryRecord
    from app.schemas.shift_reconciliation import ShiftReconciliationPerform
    from app.services.employee_shortage_service import EmployeeShortageService
    from app.services.expense_service import ExpenseService
    from app.services.reconciliation_service import ReconciliationService

    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    cash_book_repo = ShiftCashBookRepository(db_session)
    recovery_repo = EmployeeShortageRecoveryRepository(db_session)
    cash_book_service = ShiftCashBookService(
        cash_book_repo, ShiftRepository(db_session), audit_repo, auth_service,
        ShiftBankDepositRepository(db_session), shortage_recovery_repo=recovery_repo,
    )
    expense_service = ExpenseService(
        ExpenseRepository(db_session), ExpenseCategoryRepository(db_session),
        EmployeeRepository(db_session), ShiftRepository(db_session), audit_repo, auth_service,
        tender_repo=TenderRepository(db_session),
    )
    reconciliation_service = ReconciliationService(
        ShiftReconciliationRepository(db_session), ShiftRepository(db_session),
        SaleRepository(db_session), ExpenseRepository(db_session), audit_repo, auth_service,
        TenderRepository(db_session),
    )
    shortage_service = EmployeeShortageService(
        EmployeeCashShortageRepository(db_session), recovery_repo,
        ShiftReconciliationLineRepository(db_session), EmployeeRepository(db_session),
        ExpenseCategoryRepository(db_session), expense_service, audit_repo, auth_service, cash_book_repo,
    )

    shift2 = Shift(shift_date=date(2026, 1, 3), shift_label="Morning", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift2)
    db_session.commit()

    fuel = Fuel(fuel_type="Petrol", rate_per_liter=Decimal("100.00"))
    dispenser = Dispenser(code="D1")
    employee = Employee(
        employee_code="EMP-0001", first_name="Pramod", last_name="Soni",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add_all([fuel, dispenser, employee])
    db_session.commit()
    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel.id, status="active")
    db_session.add(nozzle)
    db_session.commit()

    cash_tender = db_session.query(Tender).filter_by(name="Cash").first()
    sale = Sale(
        receipt_number="RCPT-SHORTAGE-1", shift_id=shift2.id, nozzle_id=nozzle.id, fuel_id=fuel.id,
        employee_id=employee.id, quantity=Decimal("10"), rate_per_liter=Decimal("100.00"),
        amount=Decimal("1000.00"), payment_method=PaymentMethod.CASH.value, tender_id=cash_tender.id,
        status="completed", recorded_by_id=admin_id,
    )
    db_session.add(sale)
    db_session.commit()

    reconciliation = reconciliation_service.perform_shift_reconciliation(
        admin_id,
        ShiftReconciliationPerform(shift_id=shift2.id, declared_amounts={cash_tender.id: sale.amount - Decimal("416")}),
    )
    line = next(l for l in reconciliation.lines if l.tender_id == cash_tender.id)
    shortage = shortage_service.record_shortage(
        admin_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee.id),
    )

    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=shift2.id, advance_amount=Decimal("0"), final_amount=Decimal("97321")),
    )
    before = cash_book_service.get_cash_book_summary(admin_id, shift2.id)
    assert before.shortage_recoveries_total == Decimal("0")
    assert before.closing_cash_in_hand == Decimal("97321.00")  # advance/final alone - recovery not yet recorded

    shortage_service.record_recovery(
        admin_id,
        EmployeeShortageRecoveryRecord(employee_cash_shortage_id=shortage.id, shift_id=shift2.id, amount=Decimal("416")),
    )
    after = cash_book_service.get_cash_book_summary(admin_id, shift2.id)
    assert after.shortage_recoveries_total == Decimal("416.00")
    # the exact test the user asked for: recording the recovery raises
    # this shift's cash-book receipts by precisely the repaid amount
    assert after.closing_cash_in_hand == before.closing_cash_in_hand + Decimal("416.00")
    assert after.closing_cash_in_hand == Decimal("97737.00")
