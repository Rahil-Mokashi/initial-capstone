"""Model package for Petrol Pump ERP."""

from .fuel import Fuel
from .permission import Permission
from .role import Role
from .user import User

__all__ = [
    "Fuel",
    "Permission",
    "Role",
    "User",
]
