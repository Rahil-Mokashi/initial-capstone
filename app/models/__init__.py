"""Model package for Petrol Pump ERP."""

from .attendance import Attendance
from .audit_log import AuditLog
from .dispenser import Dispenser
from .employee import Employee
from .employee_document import EmployeeDocument
from .fuel import Fuel
from .fuel_reconciliation import FuelReconciliation
from .nozzle import Nozzle
from .nozzle_assignment import NozzleAssignment
from .permission import Permission
from .role import Role
from .role_permission import role_permissions
from .shift import Shift
from .tank import Tank
from .tank_reading import TankReading
from .tank_transaction import TankTransaction
from .user import User
from .user_session import UserSession

__all__ = [
    "Attendance",
    "AuditLog",
    "Dispenser",
    "Employee",
    "EmployeeDocument",
    "Fuel",
    "FuelReconciliation",
    "Nozzle",
    "NozzleAssignment",
    "Permission",
    "Role",
    "Shift",
    "Tank",
    "TankReading",
    "TankTransaction",
    "User",
    "UserSession",
    "role_permissions",
]
