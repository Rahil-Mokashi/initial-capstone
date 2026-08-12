from sqlalchemy import Table, Column, String, ForeignKey
from app.database.base import Base


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", String(36), ForeignKey("roles.id"), primary_key=True, nullable=False),
    Column("permission_id", String(36), ForeignKey("permissions.id"), primary_key=True, nullable=False),
)
