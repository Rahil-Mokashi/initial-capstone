"""
Database connection module for Petrol Pump ERP.

Handles SQLAlchemy engine creation, session management,
and database connection pooling for offline operation.
"""

import os
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from app.database.base import Base

# Import all models so SQLAlchemy can register table metadata before create_all().
import app.models  # noqa: F401


def get_database_path() -> str:
    """Return the database path from environment or default location."""
    return os.environ.get(
        "PETROL_PUMP_DB_PATH",
        os.path.join(os.path.dirname(__file__), "..", "petrol_pump.db"),
    )


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
    Initialize the database and create all tables.
    Should be called once during application startup.
    """
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    # Initialize the database
    init_db()
    print(f"Database initialized at: {DB_PATH}")
