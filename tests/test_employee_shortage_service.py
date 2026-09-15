from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import CASH_SHORTAGE_EXPENSE_CATEGORY_NAME, PaymentMethod, ShiftStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
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
from app.repositories.employee_cash_shortage_repository import EmployeeCashShortageRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.employee_shortage_recovery_repository import EmployeeShortageRecoveryRepository
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_cash_book_repository import ShiftCashBookRepository
from app.repositories.shift_reconciliation_line_repository import ShiftReconciliationLineRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tender_repository import TenderRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.employee_cash_shortage import EmployeeCashShortageRecord, EmployeeShortageRecoveryRecord
from app.schemas.sale import SaleCreate
from app.schemas.shift_reconciliation import ShiftReconciliationPerform
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.employee_shortage_service import EmployeeShortageService
from app.services.expense_service import ExpenseService
from app.services.reconciliation_service import ReconciliationService
from app.services.sale_service import SaleService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_employee_shortage.db")
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
def manager_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.MANAGER.value, "manager1").id


@pytest.fixture()
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


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
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def tank_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return TankService(
        TankRepository(db_session), TankReadingRepository(db_session), TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session), FuelRepository(db_session), EmployeeRepository(db_session),
        audit_repo, auth_service,
    )


@pytest.fixture()
def tank_id(tank_service, admin_id, fuel_id):
    tank = tank_service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=20000.0, opening_stock=10000.0))
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
    shift = Shift(shift_date=date.today(), shift_label="Morning", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift)
    db_session.commit()
    return shift.id


@pytest.fixture()
def credit_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return CreditService(
        CreditAccountRepository(db_session), CustomerPaymentRepository(db_session),
        CustomerRepository(db_session), SaleRepository(db_session), audit_repo, auth_service,
    )


@pytest.fixture()
def sale_service(db_session, tank_service, credit_service, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return SaleService(
        SaleRepository(db_session), ShiftRepository(db_session), NozzleRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), CustomerRepository(db_session),
        TankRepository(db_session), tank_service, audit_repo, auth_service, PaymentRepository(db_session),
        credit_service, tender_repo=TenderRepository(db_session),
    )


@pytest.fixture()
def expense_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ExpenseService(
        ExpenseRepository(db_session), ExpenseCategoryRepository(db_session),
        EmployeeRepository(db_session), ShiftRepository(db_session), audit_repo, auth_service,
        tender_repo=TenderRepository(db_session),
    )


@pytest.fixture()
def reconciliation_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ReconciliationService(
        ShiftReconciliationRepository(db_session), ShiftRepository(db_session),
        SaleRepository(db_session), ExpenseRepository(db_session), audit_repo, auth_service,
        TenderRepository(db_session),
    )


@pytest.fixture()
def cash_book_repo(db_session):
    return ShiftCashBookRepository(db_session)


@pytest.fixture()
def employee_shortage_service(db_session, auth_service, expense_service, cash_book_repo):
    audit_repo = AuditLogRepository(db_session)
    return EmployeeShortageService(
        EmployeeCashShortageRepository(db_session),
        EmployeeShortageRecoveryRepository(db_session),
        ShiftReconciliationLineRepository(db_session),
        EmployeeRepository(db_session),
        ExpenseCategoryRepository(db_session),
        expense_service,
        audit_repo,
        auth_service,
        cash_book_repo,
    )


def make_cash_book(cash_book_repo, admin_id, shift_id):
    """A recovery needs somewhere real to land - the same requirement
    ShiftBankDeposit already has (record advance/final first)."""
    from app.models.shift_cash_book import ShiftCashBook

    return cash_book_repo.add(ShiftCashBook(shift_id=shift_id, recorded_by_id=admin_id))


def make_sale(sale_service, admin_id, shift_id, nozzle_id, employee_id, quantity=Decimal("10"), method=PaymentMethod.CASH):
    return sale_service.create_sale(
        admin_id,
        SaleCreate(shift_id=shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=quantity, payment_method=method),
    )


def get_line(reconciliation, tender_name: str):
    return next(l for l in reconciliation.lines if l.tender.name == tender_name)


@pytest.fixture()
def cash_tender_id(db_session):
    return TenderRepository(db_session).get_by_name("Cash").id


def make_cash_shortage_line(reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id, shortfall=Decimal("100")):
    """Books a cash sale, then reconciles with less declared than
    expected, producing a genuine, unbooked cash-shortage line."""
    sale = make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id)
    reconciliation = reconciliation_service.perform_shift_reconciliation(
        admin_id,
        ShiftReconciliationPerform(shift_id=open_shift_id, declared_amounts={cash_tender_id: sale.amount - shortfall}),
    )
    return get_line(reconciliation, "Cash")


# --------------------------------------------------------------------
# record_shortage
# --------------------------------------------------------------------

def test_record_shortage_books_expense_and_receivable(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
        shortfall=Decimal("100"),
    )

    shortage = employee_shortage_service.record_shortage(
        manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
    )

    assert shortage.amount == Decimal("100.00")
    assert shortage.employee_id == employee_id
    assert shortage.expense.amount == Decimal("100.00")
    assert shortage.expense.category.name == CASH_SHORTAGE_EXPENSE_CATEGORY_NAME
    assert shortage.expense.employee_id == employee_id
    assert employee_shortage_service.get_outstanding_balance(manager_id, shortage.id) == Decimal("100.00")


def test_cannot_record_shortage_twice_for_the_same_line(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
    )
    employee_shortage_service.record_shortage(
        manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
    )
    with pytest.raises(ConflictError):
        employee_shortage_service.record_shortage(
            manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
        )


def test_record_shortage_rejects_a_line_with_no_shortage(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    sale = make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id)
    reconciliation = reconciliation_service.perform_shift_reconciliation(
        admin_id,
        ShiftReconciliationPerform(shift_id=open_shift_id, declared_amounts={cash_tender_id: sale.amount}),
    )
    line = get_line(reconciliation, "Cash")

    with pytest.raises(ValueError):
        employee_shortage_service.record_shortage(
            manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
        )


def test_record_shortage_rejects_a_non_immediate_cash_tender(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, db_session,
):
    card_tender_id = TenderRepository(db_session).get_by_name("Card").id
    sale = make_sale(sale_service, admin_id, open_shift_id, nozzle_id, employee_id, method=PaymentMethod.CARD)
    reconciliation = reconciliation_service.perform_shift_reconciliation(
        admin_id,
        ShiftReconciliationPerform(shift_id=open_shift_id, declared_amounts={card_tender_id: sale.amount - Decimal("50")}),
    )
    line = get_line(reconciliation, "Card")

    with pytest.raises(ValueError):
        employee_shortage_service.record_shortage(
            manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
        )


def test_record_shortage_unknown_line_raises_not_found(employee_shortage_service, manager_id, employee_id):
    with pytest.raises(NotFoundError):
        employee_shortage_service.record_shortage(
            manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id="does-not-exist", employee_id=employee_id),
        )


def test_record_shortage_unknown_employee_raises_not_found(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
    )
    with pytest.raises(NotFoundError):
        employee_shortage_service.record_shortage(
            manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id="does-not-exist"),
        )


def test_accountant_cannot_record_shortage(
    employee_shortage_service, reconciliation_service, sale_service, accountant_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    """SHORTAGE_MANAGE is a dedicated permission, granted the same roles
    as CREDIT_MANAGE (Manager, not Accountant) - see app/core/
    constants.py's own comment on Permission.SHORTAGE_MANAGE."""
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
    )
    with pytest.raises(PermissionDeniedError):
        employee_shortage_service.record_shortage(
            accountant_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
        )


def test_shift_supervisor_cannot_record_shortage(
    employee_shortage_service, reconciliation_service, sale_service, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id, db_session,
):
    """SHORTAGE_MANAGE is deliberately narrower than CREDIT_MANAGE, not
    merely equal to it (2026-09-15 user decision, app/core/constants.py's
    comment on Permission.SHORTAGE_MANAGE): a shift supervisor already
    holds RECONCILIATION_MANAGE for their own shift, so letting them also
    hold SHORTAGE_MANAGE would let them name an attendant they supervise
    as responsible for a shortfall and then record that shortfall's own
    repayment - the same self-approval shape RECONCILIATION_APPROVE
    already exists to guard against."""
    supervisor = make_user(db_session, UserRole.SHIFT_SUPERVISOR.value, "supervisor1")
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
    )
    with pytest.raises(PermissionDeniedError):
        employee_shortage_service.record_shortage(
            supervisor.id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
        )


def test_list_unbooked_shortage_lines_excludes_already_booked(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
    )
    unbooked = employee_shortage_service.list_unbooked_shortage_lines(manager_id)
    assert any(l.id == line.id for l in unbooked)

    employee_shortage_service.record_shortage(
        manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
    )
    unbooked_after = employee_shortage_service.list_unbooked_shortage_lines(manager_id)
    assert not any(l.id == line.id for l in unbooked_after)


# --------------------------------------------------------------------
# record_recovery / outstanding balance
# --------------------------------------------------------------------

def test_record_recovery_reduces_outstanding_balance(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id, cash_book_repo,
):
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
        shortfall=Decimal("100"),
    )
    shortage = employee_shortage_service.record_shortage(
        manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
    )
    make_cash_book(cash_book_repo, admin_id, open_shift_id)

    employee_shortage_service.record_recovery(
        manager_id,
        EmployeeShortageRecoveryRecord(employee_cash_shortage_id=shortage.id, shift_id=open_shift_id, amount=Decimal("60")),
    )
    assert employee_shortage_service.get_outstanding_balance(manager_id, shortage.id) == Decimal("40.00")

    employee_shortage_service.record_recovery(
        manager_id,
        EmployeeShortageRecoveryRecord(employee_cash_shortage_id=shortage.id, shift_id=open_shift_id, amount=Decimal("40")),
    )
    assert employee_shortage_service.get_outstanding_balance(manager_id, shortage.id) == Decimal("0.00")


def test_recovery_lands_in_the_named_shifts_cash_book(
    employee_shortage_service, reconciliation_service, sale_service, cash_book_repo, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    """The pump's own paper report shows a shortage repayment on the
    RECEIPT side of a shift's cash book, alongside Opening Balance,
    Advance and Final - real cash arriving at the counter, not a
    reversal of the original Expense. record_recovery must therefore
    write the recovery row and stamp it onto that shift's cash book in
    one transaction, so the two can never diverge."""
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
        shortfall=Decimal("100"),
    )
    shortage = employee_shortage_service.record_shortage(
        manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
    )
    cash_book = make_cash_book(cash_book_repo, admin_id, open_shift_id)

    recovery = employee_shortage_service.record_recovery(
        manager_id,
        EmployeeShortageRecoveryRecord(employee_cash_shortage_id=shortage.id, shift_id=open_shift_id, amount=Decimal("60")),
    )

    assert recovery.shift_cash_book_id == cash_book.id
    from app.repositories.employee_shortage_recovery_repository import EmployeeShortageRecoveryRepository
    receipts = EmployeeShortageRecoveryRepository(employee_shortage_service._session).list_for_cash_book(cash_book.id)
    assert sum(r.amount for r in receipts) == Decimal("60.00")


def test_recovery_amount_must_be_positive():
    with pytest.raises(ValueError):
        EmployeeShortageRecoveryRecord(employee_cash_shortage_id="x", shift_id="s1", amount=Decimal("0"))


def test_recovery_against_unknown_shortage_raises_not_found(employee_shortage_service, manager_id):
    with pytest.raises(NotFoundError):
        employee_shortage_service.record_recovery(
            manager_id,
            EmployeeShortageRecoveryRecord(
                employee_cash_shortage_id="does-not-exist", shift_id="does-not-exist", amount=Decimal("10"),
            ),
        )


def test_recovery_against_shift_with_no_cash_book_raises_not_found(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    """A recovery has nowhere real to land until the shift's own cash
    custody (advance/final) has been recorded - the identical
    requirement ShiftCashBookService.record_bank_deposit already
    enforces for a bank deposit."""
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
        shortfall=Decimal("100"),
    )
    shortage = employee_shortage_service.record_shortage(
        manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
    )
    with pytest.raises(NotFoundError):
        employee_shortage_service.record_recovery(
            manager_id,
            EmployeeShortageRecoveryRecord(
                employee_cash_shortage_id=shortage.id, shift_id=open_shift_id, amount=Decimal("10"),
            ),
        )


def test_list_for_employee_and_list_all(
    employee_shortage_service, reconciliation_service, sale_service, manager_id, admin_id,
    open_shift_id, nozzle_id, employee_id, cash_tender_id,
):
    line = make_cash_shortage_line(
        reconciliation_service, sale_service, admin_id, open_shift_id, nozzle_id, employee_id, cash_tender_id,
    )
    employee_shortage_service.record_shortage(
        manager_id, EmployeeCashShortageRecord(shift_reconciliation_line_id=line.id, employee_id=employee_id),
    )

    assert len(employee_shortage_service.list_all(manager_id)) == 1
    assert len(employee_shortage_service.list_for_employee(manager_id, employee_id)) == 1
