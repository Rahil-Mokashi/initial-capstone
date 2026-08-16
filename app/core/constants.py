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
    """Values stored in TankTransaction.transaction_type (problemstatement.md #13)."""

    RECEIPT = "receipt"
    ISSUE = "issue"
    ADJUSTMENT = "adjustment"


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
    """Values stored in Sale.payment_method (problemstatement.md #16/#17)."""

    CASH = "cash"
    UPI = "upi"
    CARD = "card"
    CREDIT = "credit"


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
        Permission.INVENTORY_MANAGE,
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
    ),
    UserRole.ACCOUNTANT: (
        Permission.INVENTORY_VIEW,
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

# Automatic scheduled backups (problemstatement.md #24, Phase 18): a
# backup is taken on startup whenever the most recent one is older than
# this many hours. 24h matches "once a day" without needing a
# background scheduler thread in an app that isn't always running.
# Configurable via Settings.auto_backup_interval_hours (app/core/config.py)
# without a rebuild - see app.database.connection.init_db.
