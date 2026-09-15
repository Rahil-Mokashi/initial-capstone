"""Shared constants for roles, permissions, and policy limits."""

from enum import Enum


class UserRole(str, Enum):
    """Business roles defined in the project requirements (problemstatement.md #6)."""

    ADMIN = "ADMIN"
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    ACCOUNTANT = "ACCOUNTANT"
    SHIFT_SUPERVISOR = "SHIFT_SUPERVISOR"
    ATTENDANT = "ATTENDANT"


class Permission(str, Enum):
    """Baseline permission names. Extend as new modules are implemented."""

    USER_MANAGE = "user.manage"
    ROLE_MANAGE = "role.manage"
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_MANAGE = "inventory.manage"
    # Changing a fuel's selling price is deliberately a stricter
    # permission than routine inventory management: it silently
    # changes the revenue of every future sale, so it gets the same
    # separate-grant treatment as SHIFT_REOPEN and EXPENSE_APPROVE.
    # Installation-wide settings: the company profile that heads every
    # printed document, and operational preferences. Managing them is
    # owner/admin territory, but VIEW is granted widely because the
    # printing code needs the company profile to head a receipt whoever
    # prints it.
    SETTINGS_VIEW = "settings.view"
    SETTINGS_MANAGE = "settings.manage"
    FUEL_PRICE_VIEW = "fuel_price.view"
    FUEL_PRICE_MANAGE = "fuel_price.manage"
    AUDIT_VIEW = "audit.view"
    EMPLOYEE_VIEW = "employee.view"
    EMPLOYEE_MANAGE = "employee.manage"
    ATTENDANCE_VIEW = "attendance.view"
    ATTENDANCE_MANAGE = "attendance.manage"
    SHIFT_VIEW = "shift.view"
    SHIFT_MANAGE = "shift.manage"
    SHIFT_REOPEN = "shift.reopen"
    NOZZLE_VIEW = "nozzle.view"
    NOZZLE_MANAGE = "nozzle.manage"
    MY_ASSIGNMENT_VIEW = "my_assignment.view"
    BACKUP_MANAGE = "backup.manage"
    PROCUREMENT_VIEW = "procurement.view"
    PROCUREMENT_MANAGE = "procurement.manage"
    SALE_VIEW = "sale.view"
    SALE_MANAGE = "sale.manage"
    CREDIT_VIEW = "credit.view"
    CREDIT_MANAGE = "credit.manage"
    EXPENSE_VIEW = "expense.view"
    EXPENSE_MANAGE = "expense.manage"
    EXPENSE_APPROVE = "expense.approve"
    RECONCILIATION_VIEW = "reconciliation.view"
    RECONCILIATION_MANAGE = "reconciliation.manage"
    ANALYTICS_VIEW = "analytics.view"
    RECONCILIATION_APPROVE = "reconciliation.approve"
    # A dedicated pair, not a reuse of RECONCILIATION_MANAGE: booking a
    # shortage and chasing its repayment is a receivable lifecycle, the
    # same kind of thing CreditAccount/CustomerPayment already is under
    # CREDIT_MANAGE/CREDIT_VIEW - not the act of reconciling a shift's
    # tenders itself. SHORTAGE_VIEW is granted the same roles as
    # CREDIT_VIEW (see ROLE_PERMISSIONS) - seeing an outstanding
    # shortage isn't the sensitive act.
    #
    # SHORTAGE_MANAGE is deliberately narrower than CREDIT_MANAGE
    # itself, not merely equal to it (2026-09-15, user decision): a
    # customer receivable is a commercial arrangement, but an employee
    # cash shortage is an accusation against a named staff member that
    # follows them until repaid, so booking one sits higher than
    # routine credit work - Manager and above only, never Shift
    # Supervisor. Concretely, a supervisor reconciling their own shift
    # must not be able to both name an attendant they supervise as
    # responsible for a shortfall AND record that shortfall's own
    # repayment - the same self-approval shape RECONCILIATION_APPROVE
    # already exists to guard against for the reconciliation itself.
    # Pinned by test_shift_supervisor_cannot_record_shortage.
    SHORTAGE_VIEW = "shortage.view"
    SHORTAGE_MANAGE = "shortage.manage"


class EmployeeStatus(str, Enum):
    """Values stored in Employee.status (EntityMixin's generic status column)."""

    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class AttendanceStatus(str, Enum):
    """Values stored in Attendance.status (problemstatement.md #9)."""

    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    HALF_DAY = "half_day"
    LEAVE = "leave"
    HOLIDAY = "holiday"


class ShiftStatus(str, Enum):
    """Values stored in Shift.status (problemstatement.md #11)."""

    OPEN = "open"
    CLOSED = "closed"


class NozzleStatus(str, Enum):
    """Values stored in Nozzle.status (problemstatement.md #15)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class AssignmentStatus(str, Enum):
    """Values stored in NozzleAssignment.status (problemstatement.md #8)."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TankStatus(str, Enum):
    """Values stored in Tank.status (problemstatement.md #13)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class TankTransactionType(str, Enum):
    """Values stored in TankTransaction.transaction_type (problemstatement.md #13).

    INTERNAL_CONSUMPTION is a new type rather than ISSUE with a reason in
    remarks, deliberately: FuelReconciliation's expected-stock math
    (app/services/tank_service.py) sums transactions by exact type, and
    ISSUE's sum feeds FuelReconciliation.sold_quantity, which other parts
    of the app are entitled to read as "litres actually sold to a
    customer". Folding an internal vehicle fill-up into ISSUE would
    silently inflate that figure with fuel that generated no sale - the
    same silent-drift failure mode this type exists to close, just moved
    into a different field.

    There is deliberately no TESTING type here, corrected after an
    earlier session wrongly added one (see PROJECT_CONTEXT.md's "wrong
    turn" record): calibration/dip testing dispenses through a nozzle
    into a measured can and is poured straight back into the same tank -
    it crosses the meter but never actually leaves the tank, so it has
    no real stock movement for a TankTransaction (this model's own
    docstring: "stock moving in/out/adjusted for one tank") to record.
    Testing volume lives on NozzleAssignment.testing_volume instead,
    where it's subtracted from what SaleService.settle_assignment_cash
    bills as a sale - see that model and service for the actual fix.
    """

    RECEIPT = "receipt"
    ISSUE = "issue"
    ADJUSTMENT = "adjustment"
    # Fuel drawn from the tank for the pump's own operational use (a
    # company vehicle, a generator) rather than sold to a customer
    # (docs/daily-report-spec.md section 6 - these were previously
    # recorded only as cash expenses, with no stock movement at all).
    INTERNAL_CONSUMPTION = "internal_consumption"


class PurchaseOrderStatus(str, Enum):
    """Values stored in PurchaseOrder.status (problemstatement.md #12)."""

    DRAFT = "draft"
    PLACED = "placed"
    PARTIALLY_DELIVERED = "partially_delivered"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class FuelDeliveryStatus(str, Enum):
    """Values stored in FuelDelivery.status - the tanker-arrival-to-
    inventory-update workflow (problemstatement.md #12): Tanker Arrival ->
    Document Verification -> Fuel Quality Verification -> Pre-Dip Reading
    -> Fuel Unloading -> Post-Dip Reading -> Inventory Update."""

    ARRIVED = "arrived"
    DOCUMENTS_VERIFIED = "documents_verified"
    QUALITY_VERIFIED = "quality_verified"
    UNLOADED = "unloaded"
    REJECTED = "rejected"


class SupplierInvoiceStatus(str, Enum):
    """Values stored in SupplierInvoice.status."""

    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"


class PaymentMethod(str, Enum):
    """Values stored in Sale.payment_method (problemstatement.md #16/#17).

    Deliberately frozen at these four rather than extended to match
    docs/daily-report-spec.md's eight real tenders (Cash/Credit/Card/DTP
    Card/PhonePe/Paytm/Expenses/Other) - see Tender (app/models/tender.py)
    for why new tenders are seeded rows from here on, not new enum
    members. This enum stays exactly as-is (still driving Sale/Payment/
    Expense's existing payment_method columns, credit checks, reports,
    and UI dropdowns) while Tender/tender_id is the new, separate
    reference the settlement/reconciliation feature uses going forward -
    see PAYMENT_METHOD_TO_TENDER_NAME below for how the two relate.
    """

    CASH = "cash"
    UPI = "upi"
    CARD = "card"
    CREDIT = "credit"


class TenderSettlementType(str, Enum):
    """Values stored in Tender.settlement_type - see that model."""

    IMMEDIATE_CASH = "immediate_cash"
    BANK_SETTLED = "bank_settled"
    INVOICED_CREDIT = "invoiced_credit"


# The eight tenders docs/daily-report-spec.md's reference report actually
# shows (section 3), seeded via app/database/seed.py's _seed_tenders the
# same way DEFAULT_FUEL_TYPES is. "Expenses" is classified IMMEDIATE_CASH:
# it involves neither a multi-day bank settlement nor a customer's
# invoiced-credit cycle, so of the three settlement types it's closest to
# Cash's own timing. "Other" is BANK_SETTLED, not IMMEDIATE_CASH -
# corrected during Step 2 (PROJECT_CONTEXT.md) after a reconciliation-
# notification test caught the original classification behaving wrongly:
# "Other" exists specifically as PaymentMethod.UPI's fallback (see
# PAYMENT_METHOD_TO_TENDER_NAME below), and UPI is a digital payment
# that settles like a card, not physical cash in a till - a variance on
# it should read as a payment-mismatch warning, not a critical cash
# shortage.
DEFAULT_TENDERS = [
    ("Cash", TenderSettlementType.IMMEDIATE_CASH),
    ("Credit", TenderSettlementType.INVOICED_CREDIT),
    ("Card", TenderSettlementType.BANK_SETTLED),
    ("DTP Card", TenderSettlementType.BANK_SETTLED),
    ("PhonePe", TenderSettlementType.BANK_SETTLED),
    ("Paytm", TenderSettlementType.BANK_SETTLED),
    ("Expenses", TenderSettlementType.IMMEDIATE_CASH),
    ("Other", TenderSettlementType.BANK_SETTLED),
]

# How an existing PaymentMethod value maps onto one of the seeded
# tenders above - used both to backfill Sale/Payment/Expense.tender_id
# on historical rows (app/database/seed.py's _backfill_tender_ids) and
# to set tender_id on every new one going forward (SaleService,
# ExpenseService), so the two never drift apart. UPI maps to "Other",
# not "PhonePe" or "Paytm" - PaymentMethod.UPI has never recorded which
# app was actually used, historically or going forward through this
# same enum, so claiming either specific app would be a fabricated
# precision this project doesn't actually have. A future UI that lets
# an attendant pick a specific UPI tender by name (rather than the
# generic PaymentMethod.UPI) is what would let PhonePe/Paytm be
# attributed correctly - not implemented here (out of scope: this app
# doesn't touch Sale/Payment/Expense's existing UI entry points).
PAYMENT_METHOD_TO_TENDER_NAME = {
    PaymentMethod.CASH: "Cash",
    PaymentMethod.CARD: "Card",
    PaymentMethod.CREDIT: "Credit",
    PaymentMethod.UPI: "Other",
}

# The one seeded ExpenseCategory this project creates (app/database/
# seed.py's _seed_expense_categories) - every other category is entirely
# user-created via ExpenseService.create_category. This one exists
# because EmployeeShortageService.record_shortage needs a category to
# book the Expense side of A2's shortage-as-receivable pattern under,
# and a fixed, predictable name is safer than trusting every deployment
# to have created one identically before the feature is first used.
CASH_SHORTAGE_EXPENSE_CATEGORY_NAME = "Cash Shortage"


class SaleStatus(str, Enum):
    """Values stored in Sale.status (problemstatement.md #16: "Completed
    sales should not be deleted... use cancellation/reversal mechanisms")."""

    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REVERSED = "reversed"


class ExpenseStatus(str, Enum):
    """Values stored in Expense.status (problemstatement.md #22)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentStatus(str, Enum):
    """Values stored in Payment.status (problemstatement.md #17). Tracked
    separately from Sale.status: the fuel can be dispensed (a completed
    sale) while its settlement is still PENDING (credit) or later found to
    have FAILED/needs to be REVERSED/REFUNDED - the two lifecycles are
    related but not identical."""

    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"
    REVERSED = "reversed"
    REFUNDED = "refunded"


class VarianceClassification(str, Enum):
    """Fuel reconciliation variance classification (problemstatement.md #14).

    Never assume a variance means theft — these are graduated review
    levels, not accusations.
    """

    NORMAL = "normal"
    WARNING = "warning"
    INVESTIGATION_REQUIRED = "investigation_required"
    APPROVAL_REQUIRED = "approval_required"


# Fuel reconciliation variance thresholds (problemstatement.md #14: "Thresholds
# must be configurable"). Expressed as a percentage of expected closing stock.
FUEL_VARIANCE_WARNING_THRESHOLD_PERCENT = 0.5
FUEL_VARIANCE_INVESTIGATION_THRESHOLD_PERCENT = 1.0
FUEL_VARIANCE_APPROVAL_THRESHOLD_PERCENT = 2.0


class ReconciliationStatus(str, Enum):
    """Values stored in ShiftReconciliation.status (problemstatement.md
    #20/#21). A NORMAL/WARNING classification is auto-accepted; an
    INVESTIGATION_REQUIRED/APPROVAL_REQUIRED classification needs a
    manager/owner to sign off via approve_shift_reconciliation."""

    ACCEPTED = "accepted"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"


# Shift cash/UPI/card reconciliation variance thresholds, expressed as a
# percentage of the expected total for that payment method - same
# graduated-severity shape as the fuel reconciliation thresholds above,
# reused rather than inventing a different scale for money vs. fuel.
RECONCILIATION_VARIANCE_WARNING_THRESHOLD_PERCENT = 0.5
RECONCILIATION_VARIANCE_INVESTIGATION_THRESHOLD_PERCENT = 1.0
RECONCILIATION_VARIANCE_APPROVAL_THRESHOLD_PERCENT = 2.0

# Sales forecast (app/services/analytics_service.py): a week-over-week
# projected change beyond this magnitude is called out as a likely
# hike/dip rather than "stable" - a plain percentage band, not a
# statistical confidence interval, since the forecast itself is a
# simple linear trend, not a claim of certainty.
FORECAST_TREND_THRESHOLD_PERCENT = 5.0

# A forecast needs at least this many weeks of sales history for a fuel
# type before a trend projection is shown at all - fewer than this and
# a "trend" is just noise dressed up as a prediction.
FORECAST_MIN_WEEKS_OF_HISTORY = 3


# ADMIN and OWNER get every permission; other roles get a minimal starter set.
# Business owners should refine this matrix as each module is implemented.
ROLE_PERMISSIONS: dict[UserRole, tuple[Permission, ...]] = {
    UserRole.ADMIN: tuple(Permission),
    UserRole.OWNER: tuple(Permission),
    UserRole.MANAGER: (
        Permission.INVENTORY_VIEW,
        Permission.SETTINGS_VIEW,
        Permission.INVENTORY_MANAGE,
        Permission.FUEL_PRICE_VIEW,
        Permission.FUEL_PRICE_MANAGE,
        Permission.SETTINGS_MANAGE,
        Permission.AUDIT_VIEW,
        Permission.EMPLOYEE_VIEW,
        Permission.EMPLOYEE_MANAGE,
        Permission.ATTENDANCE_VIEW,
        Permission.ATTENDANCE_MANAGE,
        Permission.SHIFT_VIEW,
        Permission.SHIFT_MANAGE,
        Permission.SHIFT_REOPEN,
        Permission.NOZZLE_VIEW,
        Permission.NOZZLE_MANAGE,
        Permission.PROCUREMENT_VIEW,
        Permission.PROCUREMENT_MANAGE,
        Permission.SALE_VIEW,
        Permission.SALE_MANAGE,
        Permission.CREDIT_VIEW,
        Permission.CREDIT_MANAGE,
        Permission.EXPENSE_VIEW,
        Permission.EXPENSE_MANAGE,
        Permission.EXPENSE_APPROVE,
        Permission.RECONCILIATION_VIEW,
        Permission.RECONCILIATION_MANAGE,
        Permission.RECONCILIATION_APPROVE,
        Permission.ANALYTICS_VIEW,
        Permission.SHORTAGE_VIEW,
        Permission.SHORTAGE_MANAGE,
    ),
    UserRole.ACCOUNTANT: (
        Permission.INVENTORY_VIEW,
        Permission.SETTINGS_VIEW,
        Permission.FUEL_PRICE_VIEW,
        Permission.AUDIT_VIEW,
        Permission.EMPLOYEE_VIEW,
        Permission.ATTENDANCE_VIEW,
        Permission.SHIFT_VIEW,
        Permission.NOZZLE_VIEW,
        Permission.PROCUREMENT_VIEW,
        Permission.SALE_VIEW,
        Permission.CREDIT_VIEW,
        Permission.EXPENSE_VIEW,
        Permission.EXPENSE_MANAGE,
        Permission.RECONCILIATION_VIEW,
        Permission.ANALYTICS_VIEW,
    ),
    UserRole.SHIFT_SUPERVISOR: (
        Permission.INVENTORY_VIEW,
        Permission.SETTINGS_VIEW,
        Permission.FUEL_PRICE_VIEW,
        Permission.EMPLOYEE_VIEW,
        Permission.ATTENDANCE_VIEW,
        Permission.ATTENDANCE_MANAGE,
        Permission.SHIFT_VIEW,
        Permission.SHIFT_MANAGE,
        Permission.NOZZLE_VIEW,
        Permission.SALE_VIEW,
        Permission.SALE_MANAGE,
        Permission.RECONCILIATION_VIEW,
        Permission.RECONCILIATION_MANAGE,
    ),
    UserRole.ATTENDANT: (
        Permission.MY_ASSIGNMENT_VIEW,
        Permission.SETTINGS_VIEW,
        Permission.FUEL_PRICE_VIEW,
        Permission.SALE_VIEW,
        Permission.SALE_MANAGE,
    ),
}

# Password policy (problemstatement.md #39: "Implement password policy")
PASSWORD_MIN_LENGTH = 8
PASSWORD_REQUIRE_UPPER = True
PASSWORD_REQUIRE_LOWER = True
PASSWORD_REQUIRE_DIGIT = True

# Login attempt protection (problemstatement.md #39)
MAX_FAILED_LOGIN_ATTEMPTS = 5

# How long an automatic lockout lasts before the account unlocks itself.
# This is the desktop equivalent of a web app's login rate limit: there is
# no HTTP endpoint to throttle, but guessing a password is still the way
# in, and the lockout is the only brake on it.
#
# It must EXPIRE. Previously a lockout was permanent until an admin
# cleared it, which on a pump running a night shift with no admin present
# meant a fat-fingered attendant could not record sales for hours - so the
# security control became an availability outage, and the predictable
# response is for staff to share one never-locked login, which is worse
# than the attack it was defending against.
#
# 15 minutes makes online guessing hopeless (5 attempts per 15 minutes is
# ~480 a day against a policy-enforced password) while costing an honest
# user a coffee break at worst.
LOCKOUT_DURATION_MINUTES = 15

# How old the newest off-device backup may get before the Backups screen
# starts warning about it. Every backup the app takes lands next to the
# database, so a dead drive, a theft or ransomware would take both - and
# with no cloud replica by design, an off-device copy is the only real
# protection. Seven days is a nag interval, not a policy: a pump has no IT
# staff, so a visible reminder beats a scheduler that silently never fires.
OFFSITE_BACKUP_STALE_AFTER_DAYS = 7

# Session management default, overridable via Settings.session_timeout_hours
DEFAULT_SESSION_TIMEOUT_HOURS = 8

# Site layout rule (confirmed by the user 2026-08-15): the number of
# dispensers at a pump varies, but every dispenser has exactly two nozzles.
# Each nozzle can dispense any single fuel type (commonly Petrol, Diesel, or
# Power/premium) — enforced in NozzleService.create_nozzle.
MAX_NOZZLES_PER_DISPENSER = 2

# Default fuel types seeded so nozzle/tank setup has something to select
# out of the box. Rates are left at 0.0 deliberately — real prices must be
# configured by the site, never guessed.
DEFAULT_FUEL_TYPES = ["Petrol", "Diesel", "Power"]

# Dashboard low-stock flag: a tank at or below this percent of its capacity
# is surfaced as needing attention. A flag, not an alarm - matches the
# non-accusatory tone already used for reconciliation variance.
DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT = 20.0


class NotificationSeverity(str, Enum):
    """Graduated severity for local application alerts (problemstatement.md
    #43).

    Three levels, not five: the point of severity here is to decide what
    sorts to the top of one screen, and a scale finer than the decisions it
    drives is noise. The same reasoning that kept the discrepancy workflow
    to a single approval action rather than a multi-stage ticket system.

    Deliberately a separate scale from VarianceClassification. That one
    answers "how far out is this reconciliation, and who must sign it off";
    this one answers "how loudly should the app mention it". A fuel
    variance maps INTO this scale (see NotificationService) but the two are
    not the same question, and collapsing them would mean every future
    alert type had to pretend to be a variance.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class NotificationCategory(str, Enum):
    """The alert types enumerated in problemstatement.md #43.

    Kept as an enum rather than free-text titles so the UI can group and
    filter on a stable key, and so a typo cannot silently invent a
    fourteenth category that nothing displays.
    """

    LOW_FUEL = "low_fuel"
    FUEL_VARIANCE = "fuel_variance"
    CASH_SHORTAGE = "cash_shortage"
    CASH_EXCESS = "cash_excess"
    PAYMENT_MISMATCH = "payment_mismatch"
    FAILED_RECONCILIATION = "failed_reconciliation"
    ATTENDANCE_ISSUE = "attendance_issue"
    UNAUTHORIZED_ACTION = "unauthorized_action"
    PENDING_APPROVAL = "pending_approval"
    OUTSTANDING_CREDIT = "outstanding_credit"
    SUPPLIER_PAYMENT_DUE = "supplier_payment_due"
    BACKUP_FAILURE = "backup_failure"
    DATABASE_ERROR = "database_error"


# How far back the event-derived alerts (unauthorized action, database
# error) look. Those two are the only categories that describe a moment
# rather than a standing condition, so unlike the others they cannot
# clear themselves when the situation improves - they age out instead.
# A week is long enough that a Monday morning still shows what happened
# over the weekend.
NOTIFICATION_RECENT_EVENT_DAYS = 7

# A backup is treated as failing once the newest one is older than this.
# Deliberately derived from the absence of a recent backup file rather
# than from a "backup failed" event record: the file's absence is the
# consequence that actually matters, and it catches every cause - a full
# disk, a permission change, a crash before the write, or a code path
# nobody remembered to add logging to.
#
# Twice AUTO_BACKUP_INTERVAL_HOURS (24h), so one missed daily backup is
# not yet an alert but two consecutive misses are.
NOTIFICATION_BACKUP_OVERDUE_HOURS = 48

# At most this many individual alerts per category, with a summary line
# standing in for the rest. Twenty low-stock tanks must not push a
# database error off the screen - an alert list nobody can scan is an
# alert list nobody reads.
NOTIFICATION_MAX_PER_CATEGORY = 5

# Automatic scheduled backups (problemstatement.md #24, Phase 18): a
# backup is taken on startup whenever the most recent one is older than
# this many hours. 24h matches "once a day" without needing a
# background scheduler thread in an app that isn't always running.
# Configurable via Settings.auto_backup_interval_hours (app/core/config.py)
# without a rebuild - see app.database.connection.init_db.
