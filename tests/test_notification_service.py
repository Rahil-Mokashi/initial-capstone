"""Tests for the local application alerts (problemstatement.md #43).

The point worth testing hardest is not that an alert appears - it is
that an alert DISAPPEARS once the condition it describes stops being
true. That property is the whole justification for deriving alerts from
live data instead of storing rows in a `notifications` table, so if it
is not tested, the design decision is not actually protected against a
future change that quietly reintroduces stored state.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import (
    ExpenseStatus,
    NotificationCategory,
    NotificationSeverity,
    ReconciliationStatus,
    SupplierInvoiceStatus,
    UserRole,
    VarianceClassification,
)
from app.core.exceptions import PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.credit_account import CreditAccount
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.expense import Expense, ExpenseCategory
from app.models.fuel import Fuel
from app.models.fuel_reconciliation import FuelReconciliation
from app.models.role import Role
from app.models.shift import Shift
from app.models.shift_reconciliation import ShiftReconciliation
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from app.models.tank import Tank
from app.models.user import User
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
from app.repositories.supplier_invoice_repository import SupplierInvoiceRepository, SupplierPaymentRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.notification_service import NotificationService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_notifications.db")
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
def attendant_id(db_session, admin_id):
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def supervisor_id(db_session, admin_id):
    return make_user(db_session, UserRole.SHIFT_SUPERVISOR.value, "supervisor1").id


@pytest.fixture()
def auth_service(db_session):
    return AuthService(
        UserRepository(db_session), AuditLogRepository(db_session), UserSessionRepository(db_session)
    )


@pytest.fixture()
def notification_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    credit_service = CreditService(
        CreditAccountRepository(db_session),
        CustomerPaymentRepository(db_session),
        CustomerRepository(db_session),
        SaleRepository(db_session),
        audit_repo,
        auth_service,
    )
    return NotificationService(
        tank_repo=TankRepository(db_session),
        fuel_reconciliation_repo=FuelReconciliationRepository(db_session),
        shift_reconciliation_repo=ShiftReconciliationRepository(db_session),
        expense_repo=ExpenseRepository(db_session),
        employee_repo=EmployeeRepository(db_session),
        attendance_repo=AttendanceRepository(db_session),
        credit_account_repo=CreditAccountRepository(db_session),
        supplier_invoice_repo=SupplierInvoiceRepository(db_session),
        supplier_payment_repo=SupplierPaymentRepository(db_session),
        audit_repo=audit_repo,
        credit_service=credit_service,
        auth_service=auth_service,
        db_path=None,  # the backup producer is exercised separately
    )


@pytest.fixture()
def employee(db_session):
    record = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1), status="active",
    )
    db_session.add(record)
    db_session.commit()
    return record


def categories(summary) -> set:
    return {n.category for n in summary.notifications}


# ----------------------------------------------------------------------
# Low fuel
# ----------------------------------------------------------------------


def make_tank(db_session, code: str, capacity: str, current: str) -> Tank:
    fuel = db_session.query(Fuel).first()
    if fuel is None:
        fuel = Fuel(fuel_type="Petrol", rate_per_liter=Decimal("100.00"))
        db_session.add(fuel)
        db_session.commit()
    tank = Tank(
        code=code,
        fuel_id=fuel.id,
        capacity=Decimal(capacity),
        current_stock=Decimal(current),
        opening_stock=Decimal(current),
        status="active",
    )
    db_session.add(tank)
    db_session.commit()
    return tank


def test_low_fuel_alert_appears_below_the_threshold(notification_service, admin_id, db_session):
    make_tank(db_session, "T1", "20000", "2000")  # 10% - below the 20% flag
    summary = notification_service.get_notifications(admin_id)
    assert NotificationCategory.LOW_FUEL in categories(summary)


def test_a_full_tank_raises_no_alert(notification_service, admin_id, db_session):
    make_tank(db_session, "T1", "20000", "18000")  # 90%
    summary = notification_service.get_notifications(admin_id)
    assert NotificationCategory.LOW_FUEL not in categories(summary)


def test_the_low_fuel_alert_clears_when_the_tank_is_refilled(notification_service, admin_id, db_session):
    """The central property of a derived alert list.

    A stored notification row would still be sitting there after the
    refill unless something expired it. Deriving the alert means the
    refill IS the fix, with no second mechanism to keep in step.
    """
    tank = make_tank(db_session, "T1", "20000", "1000")
    assert NotificationCategory.LOW_FUEL in categories(notification_service.get_notifications(admin_id))

    tank.current_stock = Decimal("19000")
    db_session.commit()

    assert NotificationCategory.LOW_FUEL not in categories(notification_service.get_notifications(admin_id))


def test_a_nearly_empty_tank_is_critical_not_merely_a_warning(notification_service, admin_id, db_session):
    make_tank(db_session, "T1", "20000", "1000")  # 5% - under half the 20% flag
    alert = next(
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.LOW_FUEL
    )
    assert alert.severity == NotificationSeverity.CRITICAL


# ----------------------------------------------------------------------
# Permission gating
# ----------------------------------------------------------------------


def test_an_attendant_is_not_told_about_tanks_they_cannot_open(notification_service, attendant_id, db_session):
    make_tank(db_session, "T1", "20000", "500")
    summary = notification_service.get_notifications(attendant_id)
    assert NotificationCategory.LOW_FUEL not in categories(summary)


def test_a_supervisor_without_approve_rights_gets_no_approval_alerts(
    notification_service, supervisor_id, admin_id, db_session
):
    """RECONCILIATION_APPROVE is deliberately withheld from Shift
    Supervisor (they perform reconciliations, a manager signs off the
    high-variance ones), so a "waiting for you" alert must not reach
    them - it would be waiting for somebody else."""
    add_reconciliation(db_session, admin_id, status=ReconciliationStatus.PENDING_APPROVAL.value)
    summary = notification_service.get_notifications(supervisor_id)
    assert NotificationCategory.PENDING_APPROVAL not in categories(summary)


# ----------------------------------------------------------------------
# Shift reconciliation: shortage / excess / mismatch / needs approval
# ----------------------------------------------------------------------


def add_reconciliation(
    db_session,
    performed_by_id,
    cash_variance="0",
    upi_variance="0",
    card_variance="0",
    status=ReconciliationStatus.ACCEPTED.value,
    classification=VarianceClassification.NORMAL.value,
) -> ShiftReconciliation:
    shift = Shift(
        shift_date=date.today(),
        shift_label=f"Shift-{db_session.query(Shift).count() + 1}",
        opened_by_id=performed_by_id,
        status="closed",
    )
    db_session.add(shift)
    db_session.commit()

    reconciliation = ShiftReconciliation(
        shift_id=shift.id,
        expected_cash=Decimal("1000"), declared_cash=Decimal("1000") + Decimal(cash_variance),
        cash_variance=Decimal(cash_variance),
        expected_upi=Decimal("500"), declared_upi=Decimal("500") + Decimal(upi_variance),
        upi_variance=Decimal(upi_variance),
        expected_card=Decimal("500"), declared_card=Decimal("500") + Decimal(card_variance),
        card_variance=Decimal(card_variance),
        classification=classification,
        status=status,
        performed_by_id=performed_by_id,
    )
    db_session.add(reconciliation)
    db_session.commit()
    return reconciliation


def test_cash_shortage_is_reported_as_critical(notification_service, admin_id, db_session):
    add_reconciliation(db_session, admin_id, cash_variance="-250")
    alert = next(
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.CASH_SHORTAGE
    )
    assert alert.severity == NotificationSeverity.CRITICAL


def test_cash_excess_is_reported_separately_and_less_severely(notification_service, admin_id, db_session):
    """Money over is still a discrepancy - usually an unrecorded sale -
    but it is not a loss, so it must not carry the same weight as a
    shortage."""
    add_reconciliation(db_session, admin_id, cash_variance="250")
    found = categories(notification_service.get_notifications(admin_id))
    assert NotificationCategory.CASH_EXCESS in found
    assert NotificationCategory.CASH_SHORTAGE not in found


def test_a_balanced_reconciliation_raises_nothing(notification_service, admin_id, db_session):
    add_reconciliation(db_session, admin_id)
    found = categories(notification_service.get_notifications(admin_id))
    assert NotificationCategory.CASH_SHORTAGE not in found
    assert NotificationCategory.CASH_EXCESS not in found
    assert NotificationCategory.PAYMENT_MISMATCH not in found


def test_digital_payment_mismatch_is_reported(notification_service, admin_id, db_session):
    add_reconciliation(db_session, admin_id, upi_variance="-40")
    assert NotificationCategory.PAYMENT_MISMATCH in categories(notification_service.get_notifications(admin_id))


def test_a_reconciliation_awaiting_approval_is_flagged(notification_service, admin_id, db_session):
    add_reconciliation(
        db_session, admin_id,
        status=ReconciliationStatus.PENDING_APPROVAL.value,
        classification=VarianceClassification.APPROVAL_REQUIRED.value,
    )
    summary = notification_service.get_notifications(admin_id)
    assert NotificationCategory.FAILED_RECONCILIATION in categories(summary)
    assert NotificationCategory.PENDING_APPROVAL in categories(summary)


def test_an_old_settled_reconciliation_is_not_reported_forever(notification_service, admin_id, db_session):
    """An approved reconciliation from months ago is history, not an
    alert. Surfacing it permanently would train the operator to ignore
    the screen, which costs more than the alert is worth."""
    from datetime import datetime, timezone

    reconciliation = add_reconciliation(db_session, admin_id, cash_variance="-250")
    reconciliation.performed_at = datetime.now(timezone.utc) - timedelta(days=90)
    db_session.commit()

    assert NotificationCategory.CASH_SHORTAGE not in categories(
        notification_service.get_notifications(admin_id)
    )


def test_an_unresolved_reconciliation_is_reported_however_old_it_is(notification_service, admin_id, db_session):
    """The mirror of the previous test: ageing out must never silently
    drop something nobody has dealt with."""
    from datetime import datetime, timezone

    reconciliation = add_reconciliation(
        db_session, admin_id, cash_variance="-250", status=ReconciliationStatus.PENDING_APPROVAL.value
    )
    reconciliation.performed_at = datetime.now(timezone.utc) - timedelta(days=90)
    db_session.commit()

    assert NotificationCategory.CASH_SHORTAGE in categories(
        notification_service.get_notifications(admin_id)
    )


# ----------------------------------------------------------------------
# Fuel variance
# ----------------------------------------------------------------------


def test_fuel_variance_uses_only_the_latest_reconciliation(notification_service, admin_id, db_session):
    """A tank that was out of tolerance last week and clean today is
    fine. Re-raising the superseded one would mean a variance could
    never be cleared by doing the correct thing."""
    tank = make_tank(db_session, "T1", "20000", "15000")
    for offset, classification in (
        (5, VarianceClassification.APPROVAL_REQUIRED.value),
        (1, VarianceClassification.NORMAL.value),
    ):
        db_session.add(
            FuelReconciliation(
                tank_id=tank.id,
                reconciliation_date=date.today() - timedelta(days=offset),
                opening_stock=Decimal("16000"), received_quantity=Decimal("0"),
                sold_quantity=Decimal("1000"), expected_closing_stock=Decimal("15000"),
                physical_stock=Decimal("15000"), variance=Decimal("0"),
                variance_percent=Decimal("0"), classification=classification,
                performed_by_id=admin_id,
            )
        )
    db_session.commit()

    assert NotificationCategory.FUEL_VARIANCE not in categories(
        notification_service.get_notifications(admin_id)
    )


def test_a_current_fuel_variance_is_reported(notification_service, admin_id, db_session):
    tank = make_tank(db_session, "T1", "20000", "15000")
    db_session.add(
        FuelReconciliation(
            tank_id=tank.id,
            reconciliation_date=date.today(),
            opening_stock=Decimal("16000"), received_quantity=Decimal("0"),
            sold_quantity=Decimal("1000"), expected_closing_stock=Decimal("15000"),
            physical_stock=Decimal("14800"), variance=Decimal("-200"),
            variance_percent=Decimal("1.33"),
            classification=VarianceClassification.APPROVAL_REQUIRED.value,
            performed_by_id=admin_id,
        )
    )
    db_session.commit()

    alert = next(
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.FUEL_VARIANCE
    )
    assert alert.severity == NotificationSeverity.CRITICAL
    # Tone matters here: the project's rule is that a variance is never
    # treated as an accusation of theft.
    assert "not an accusation" in alert.detail


# ----------------------------------------------------------------------
# Attendance, approvals, credit, procurement
# ----------------------------------------------------------------------


def test_an_employee_with_no_attendance_today_is_flagged(notification_service, admin_id, employee):
    summary = notification_service.get_notifications(admin_id)
    assert NotificationCategory.ATTENDANCE_ISSUE in categories(summary)


def test_the_attendance_alert_clears_once_the_employee_is_marked(
    notification_service, admin_id, employee, db_session
):
    """Reports a MISSING record, not a bad one: an employee marked
    absent has been accounted for, while one with no row at all is the
    gap a supervisor can still close today."""
    from app.models.attendance import Attendance

    assert NotificationCategory.ATTENDANCE_ISSUE in categories(
        notification_service.get_notifications(admin_id)
    )

    db_session.add(
        Attendance(
            employee_id=employee.id, attendance_date=date.today(),
            status="absent", supervisor_id=admin_id,
        )
    )
    db_session.commit()

    assert NotificationCategory.ATTENDANCE_ISSUE not in categories(
        notification_service.get_notifications(admin_id)
    )


def test_pending_expenses_are_rolled_up_into_one_alert(notification_service, admin_id, db_session, employee):
    """Three pending expenses are one action ("review the queue"), so
    they must not become three separate alerts."""
    category = ExpenseCategory(name="Fuel testing", status="active")
    db_session.add(category)
    db_session.commit()
    for index in range(3):
        db_session.add(
            Expense(
                category_id=category.id, amount=Decimal("100"), expense_date=date.today(),
                payment_method="cash", status=ExpenseStatus.PENDING.value, recorded_by_id=admin_id,
                employee_id=employee.id, description=f"Expense {index}",
            )
        )
    db_session.commit()

    pending = [
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.PENDING_APPROVAL
    ]
    assert len(pending) == 1
    assert "3 expense(s)" in pending[0].title


def test_an_overdue_credit_account_is_reported(notification_service, admin_id, db_session, employee):
    """A credit sale older than the account's agreed term, still unpaid.

    Built through real rows rather than a stub because the overdue rule
    reads the sale's own sale_at and the account's payment_due_days -
    faking either would test the mock, not the rule.
    """
    from datetime import datetime, timezone

    from app.models.dispenser import Dispenser
    from app.models.nozzle import Nozzle
    from app.models.sale import Sale

    fuel = db_session.query(Fuel).first()
    if fuel is None:
        fuel = Fuel(fuel_type="Petrol", rate_per_liter=Decimal("100.00"))
        db_session.add(fuel)
        db_session.commit()

    dispenser = Dispenser(code="D1", status="active")
    db_session.add(dispenser)
    db_session.commit()
    nozzle = Nozzle(code="N1", dispenser_id=dispenser.id, fuel_id=fuel.id, status="active")
    shift = Shift(
        shift_date=date.today(), shift_label="Morning", opened_by_id=admin_id, status="closed"
    )
    customer = Customer(name="Sharma Transport", status="active")
    db_session.add_all([nozzle, shift, customer])
    db_session.commit()

    db_session.add(
        CreditAccount(
            customer_id=customer.id, credit_limit=Decimal("50000"),
            payment_due_days=15, created_by_id=admin_id,
        )
    )
    db_session.add(
        Sale(
            receipt_number="RCP-0001", shift_id=shift.id, nozzle_id=nozzle.id,
            fuel_id=fuel.id, employee_id=employee.id, customer_id=customer.id,
            quantity=Decimal("100"), rate_per_liter=Decimal("100"), amount=Decimal("10000"),
            payment_method="credit", status="completed", recorded_by_id=admin_id,
            sale_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
    )
    db_session.commit()

    alert = next(
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.OUTSTANDING_CREDIT
    )
    assert "Sharma Transport" in alert.title
    # Same non-accusatory tone the project applies to variance.
    assert "not an accusation" in alert.detail


def test_an_overdue_supplier_invoice_is_reported(notification_service, admin_id, db_session):
    supplier = Supplier(name="IOC Depot", status="active")
    db_session.add(supplier)
    db_session.commit()
    db_session.add(
        SupplierInvoice(
            invoice_number="INV-77", supplier_id=supplier.id,
            invoice_date=date.today() - timedelta(days=40),
            due_date=date.today() - timedelta(days=10),
            amount=Decimal("250000"), status=SupplierInvoiceStatus.UNPAID.value,
            recorded_by_id=admin_id,
        )
    )
    db_session.commit()

    alert = next(
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.SUPPLIER_PAYMENT_DUE
    )
    assert "INV-77" in alert.title


def test_an_invoice_not_yet_due_is_not_reported(notification_service, admin_id, db_session):
    supplier = Supplier(name="IOC Depot", status="active")
    db_session.add(supplier)
    db_session.commit()
    db_session.add(
        SupplierInvoice(
            invoice_number="INV-78", supplier_id=supplier.id,
            invoice_date=date.today(), due_date=date.today() + timedelta(days=20),
            amount=Decimal("250000"), status=SupplierInvoiceStatus.UNPAID.value,
            recorded_by_id=admin_id,
        )
    )
    db_session.commit()

    assert NotificationCategory.SUPPLIER_PAYMENT_DUE not in categories(
        notification_service.get_notifications(admin_id)
    )


# ----------------------------------------------------------------------
# Event-derived: unauthorized action
# ----------------------------------------------------------------------


def test_a_refused_action_is_recorded_and_then_surfaced(
    notification_service, admin_id, attendant_id, db_session, auth_service
):
    """End to end: the decorator records the denial, and the alert list
    picks it up. Before this change a denial was raised and then
    vanished, leaving nothing to distinguish one mis-click from somebody
    probing what they can reach."""
    from app.repositories.tank_reading_repository import TankReadingRepository
    from app.repositories.tank_transaction_repository import TankTransactionRepository
    from app.repositories.fuel_repository import FuelRepository
    from app.services.tank_service import TankService

    audit_repo = AuditLogRepository(db_session)
    tank_service = TankService(
        TankRepository(db_session), TankReadingRepository(db_session),
        TankTransactionRepository(db_session), FuelReconciliationRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), audit_repo, auth_service,
    )

    with pytest.raises(PermissionDeniedError):
        tank_service.list_tanks(attendant_id)

    denials = audit_repo.search(event_type="permission_denied")
    assert len(denials) == 1
    assert denials[0].actor_id == attendant_id

    assert NotificationCategory.UNAUTHORIZED_ACTION in categories(
        notification_service.get_notifications(admin_id)
    )


def test_refused_actions_are_counted_not_listed_one_by_one(
    notification_service, admin_id, attendant_id, db_session
):
    audit_repo = AuditLogRepository(db_session)
    for _ in range(4):
        audit_repo.record(event_type="permission_denied", actor_id=attendant_id, description="Denied: tank.view")

    alerts = [
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.UNAUTHORIZED_ACTION
    ]
    assert len(alerts) == 1
    assert "4 refused action(s)" in alerts[0].title


def test_many_refused_actions_escalate_to_critical(notification_service, admin_id, attendant_id, db_session):
    """One denial is a mis-click; a burst is a pattern. Severity has to
    reflect the shape rather than any single event."""
    audit_repo = AuditLogRepository(db_session)
    for _ in range(12):
        audit_repo.record(event_type="permission_denied", actor_id=attendant_id, description="Denied: tank.view")

    alert = next(
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.UNAUTHORIZED_ACTION
    )
    assert alert.severity == NotificationSeverity.CRITICAL


def test_a_failed_integrity_check_surfaces_as_a_database_error(notification_service, admin_id, db_session):
    audit_repo = AuditLogRepository(db_session)
    audit_repo.record(
        event_type="database_integrity_failed", actor_id=admin_id,
        entity_type="Database", description="row 12 missing from index",
    )
    assert NotificationCategory.DATABASE_ERROR in categories(
        notification_service.get_notifications(admin_id)
    )


def test_a_broken_audit_chain_surfaces_as_a_database_error(notification_service, admin_id, db_session):
    audit_repo = AuditLogRepository(db_session)
    audit_repo.record(
        event_type="audit_trail_tampered", actor_id=admin_id,
        entity_type="AuditLog", description="1 problem(s): entry X modified",
    )
    alert = next(
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.DATABASE_ERROR
    )
    assert alert.severity == NotificationSeverity.CRITICAL


# ----------------------------------------------------------------------
# Volume control and resilience
# ----------------------------------------------------------------------


def test_a_flood_of_one_category_is_capped_with_an_honest_count(notification_service, admin_id, db_session):
    """Twenty low tanks must not push a database error off the screen -
    but the count must still be visible, because an alert list that
    silently drops items understates the problem."""
    for index in range(9):
        make_tank(db_session, f"T{index}", "20000", "1000")

    low_fuel = [
        n for n in notification_service.get_notifications(admin_id).notifications
        if n.category == NotificationCategory.LOW_FUEL
    ]
    assert len(low_fuel) == 6  # 5 individual + 1 summary line
    assert "4 more" in low_fuel[-1].title


def test_critical_alerts_sort_above_warnings(notification_service, admin_id, db_session):
    make_tank(db_session, "T1", "20000", "1000")          # critical low fuel
    add_reconciliation(db_session, admin_id, upi_variance="-40")  # warning mismatch

    severities = [n.severity for n in notification_service.get_notifications(admin_id).notifications]
    assert severities == sorted(severities, key=lambda s: {"critical": 0, "warning": 1, "info": 2}[s.value])


def test_one_broken_producer_does_not_blank_the_whole_screen(notification_service, admin_id, db_session):
    """The alert list is consulted precisely when something is already
    wrong, which is when a query is most likely to throw. Losing one
    category beats showing an empty, falsely reassuring screen."""
    make_tank(db_session, "T1", "20000", "1000")

    class Exploding:
        def list_all(self):
            raise RuntimeError("simulated database failure")

    notification_service._supplier_invoice_repo = Exploding()

    summary = notification_service.get_notifications(admin_id)
    assert NotificationCategory.LOW_FUEL in categories(summary)
    assert NotificationCategory.SUPPLIER_PAYMENT_DUE not in categories(summary)


def test_a_clean_system_produces_no_alerts(notification_service, admin_id):
    summary = notification_service.get_notifications(admin_id)
    assert summary.total == 0
    assert summary.critical_count == 0


def test_summary_counts_match_the_list(notification_service, admin_id, db_session):
    make_tank(db_session, "T1", "20000", "1000")            # critical
    add_reconciliation(db_session, admin_id, upi_variance="-40")   # warning

    summary = notification_service.get_notifications(admin_id)
    assert summary.total == len(summary.notifications)
    assert summary.critical_count == sum(
        1 for n in summary.notifications if n.severity == NotificationSeverity.CRITICAL
    )
    assert summary.warning_count == sum(
        1 for n in summary.notifications if n.severity == NotificationSeverity.WARNING
    )
