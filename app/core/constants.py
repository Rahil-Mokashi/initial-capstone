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
    ),
    UserRole.ACCOUNTANT: (
        Permission.INVENTORY_VIEW,
        Permission.AUDIT_VIEW,
        Permission.EMPLOYEE_VIEW,
        Permission.ATTENDANCE_VIEW,
        Permission.SHIFT_VIEW,
    ),
    UserRole.SHIFT_SUPERVISOR: (
        Permission.INVENTORY_VIEW,
        Permission.EMPLOYEE_VIEW,
        Permission.ATTENDANCE_VIEW,
        Permission.ATTENDANCE_MANAGE,
        Permission.SHIFT_VIEW,
        Permission.SHIFT_MANAGE,
    ),
    UserRole.ATTENDANT: (),
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
