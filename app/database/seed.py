import uuid
from datetime import datetime, timezone

from app import database as db_package
from app.core.constants import ROLE_PERMISSIONS, Permission as PermissionName, UserRole
from app.core.security import hash_password
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User

DEFAULT_ADMIN_PASSWORD = "Admin@123"


def _seed_roles_and_permissions(session) -> dict:
    """Ensure every UserRole and Permission exists, and wire the RBAC matrix.

    Returns a dict of role name -> Role instance.
    """
    permissions_by_name = {p.name: p for p in session.query(Permission).all()}
    for perm in PermissionName:
        if perm.value not in permissions_by_name:
            permission = Permission(id=str(uuid.uuid4()), name=perm.value)
            session.add(permission)
            permissions_by_name[perm.value] = permission
    session.flush()

    roles_by_name = {r.name: r for r in session.query(Role).all()}
    for role in UserRole:
        if role.value not in roles_by_name:
            role_row = Role(
                id=str(uuid.uuid4()),
                name=role.value,
                description=f"{role.value.replace('_', ' ').title()} role",
            )
            session.add(role_row)
            roles_by_name[role.value] = role_row
    session.flush()

    for role, perms in ROLE_PERMISSIONS.items():
        role_row = roles_by_name[role.value]
        wanted = {permissions_by_name[p.value] for p in perms}
        current = set(role_row.permissions)
        for missing in wanted - current:
            role_row.permissions.append(missing)
    session.flush()

    return roles_by_name


def seed_initial_data() -> None:
    """Seed roles, permissions, and the initial admin user for the MVP run."""
    session = db_package.connection.SessionLocal()
    try:
        roles_by_name = _seed_roles_and_permissions(session)

        existing_admin = session.query(User).filter_by(username="admin").first()
        if existing_admin:
            session.commit()
            return

        now = datetime.now(timezone.utc)
        admin_user = User(
            id=str(uuid.uuid4()),
            username="admin",
            email="admin@example.com",
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            first_name="Admin",
            last_name="User",
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            role=roles_by_name[UserRole.ADMIN.value],
            created_at=now,
            updated_at=now,
        )
        session.add(admin_user)
        session.commit()
    finally:
        session.close()
