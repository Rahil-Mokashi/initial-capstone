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


class EmployeeStatus(str, Enum):
    """Values stored in Employee.status (EntityMixin's generic status column)."""

    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


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
    ),
    UserRole.ACCOUNTANT: (Permission.INVENTORY_VIEW, Permission.AUDIT_VIEW, Permission.EMPLOYEE_VIEW),
    UserRole.SHIFT_SUPERVISOR: (Permission.INVENTORY_VIEW, Permission.EMPLOYEE_VIEW),
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
