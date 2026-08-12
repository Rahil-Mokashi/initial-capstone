import uuid
from datetime import datetime, timezone

from app import database as db_package
from app.core.security import hash_password
from app.models.user import User
from app.models.role import Role


def seed_initial_data() -> None:
    """Seed basic initial data for the MVP run."""
    session = db_package.connection.SessionLocal()
    try:
        existing_admin = session.query(User).filter_by(username="admin").first()
        if existing_admin:
            return

        now = datetime.now(timezone.utc)
        admin_role = Role(
            id=str(uuid.uuid4()),
            name="admin",
            description="Administrator role with full access",
            created_at=now,
            updated_at=now,
        )
        session.add(admin_role)
        session.flush()

        admin_user = User(
            id=str(uuid.uuid4()),
            username="admin",
            email="admin@example.com",
            password_hash=hash_password("admin123"),
            first_name="Admin",
            last_name="User",
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            role=admin_role,
            created_at=now,
            updated_at=now,
        )
        session.add(admin_user)
        session.commit()
    finally:
        session.close()
