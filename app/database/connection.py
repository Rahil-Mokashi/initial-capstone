"""
Database connection module for Petrol Pump ERP.

Handles SQLAlchemy engine creation, session management,
and database connection pooling for offline operation.
"""

import os
import sys
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from app.core.logging import logger

# Import all models so SQLAlchemy can register table metadata before
# Alembic's autogenerate/upgrade compares it against the database.
import app.models  # noqa: F401


def _default_database_path() -> str:
    """Where the DB lives when PETROL_PUMP_DB_PATH isn't set.

    A PyInstaller onefile build unpacks to a fresh temp directory
    (sys._MEIPASS) on every single launch, so resolving the path relative
    to this file's location — as a normal dev checkout does — would
    silently reset the database every time the app starts once packaged.
    When frozen, use a stable per-user app-data directory instead, e.g.
    %LOCALAPPDATA%\\PetrolPumpERP on Windows, so data survives restarts
    and each install on each PC gets its own fresh, persistent database.
    """
    if getattr(sys, "frozen", False):
        base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        app_dir = os.path.join(base_dir, "PetrolPumpERP")
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, "petrol_pump.db")
    return os.path.join(os.path.dirname(__file__), "..", "petrol_pump.db")


def get_database_path() -> str:
    """Return the database path from environment or default location."""
    return os.environ.get("PETROL_PUMP_DB_PATH", _default_database_path())


# Database URL - SQLite file
DB_PATH = get_database_path()

# Create engine with SQLite-specific settings
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={
        "check_same_thread": False,
    },
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """SQLite disables foreign-key enforcement and WAL mode by default.

    Without this, every ForeignKey() in app/models is enforced only by
    application code, not by the database itself (CLAUDE.md: "Always use
    foreign keys"; problemstatement.md #24: "Enable SQLite foreign keys",
    "Use WAL mode where appropriate"). This runs on every new DBAPI
    connection, including ones opened by other engines (e.g. in tests),
    so it's guarded to only touch actual sqlite3 connections.
    """
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator:
    """
    Dependency generator for getting a database session.

    Usage:
        db = next(get_db())
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Bring the database up to the latest schema via Alembic migrations
    (CLAUDE.md: "never modify database schema without migration") rather
    than a blunt create_all() — this also applies to the very first
    launch, whose single "baseline schema" migration creates every
    table. If a schema change is actually about to be applied to a
    database that already has data in it, back it up first (CLAUDE.md:
    "backup before migrations").
    """
    from app.database import backup as backup_module
    from app.database import migrations

    # Read the module-global DB_PATH (not a fresh get_database_path()
    # call) so tests that monkeypatch app.database.connection.DB_PATH
    # directly - without also overriding PETROL_PUMP_DB_PATH - still
    # migrate the path they actually intend, not the real default one.
    db_path = DB_PATH
    db_has_data = os.path.exists(db_path) and os.path.getsize(db_path) > 0
    if db_has_data and migrations.has_pending_migrations(db_path):
        try:
            backup_path = backup_module.create_backup(db_path, reason="pre_migration")
            logger.info("Pre-migration backup created at %s", backup_path)
        except (OSError, IOError):
            logger.warning("Could not create a pre-migration backup; proceeding anyway", exc_info=True)

    migrations.upgrade_to_head(db_path)

    # Automatic scheduled backup (CLAUDE.md: "Implement automatic
    # scheduled backups") - only once there's real data to protect; a
    # freshly created, still-empty database has nothing worth backing
    # up yet. A failure here must never block the app from starting.
    if db_has_data:
        from app.core.constants import AUTO_BACKUP_INTERVAL_HOURS

        try:
            if backup_module.should_take_scheduled_backup(db_path, AUTO_BACKUP_INTERVAL_HOURS):
                backup_path = backup_module.create_backup(db_path, reason="scheduled")
                logger.info("Scheduled backup created at %s", backup_path)
        except (OSError, IOError):
            logger.warning("Could not create the scheduled backup; proceeding anyway", exc_info=True)


if __name__ == "__main__":
    # Initialize the database
    init_db()
    print(f"Database initialized at: {DB_PATH}")
