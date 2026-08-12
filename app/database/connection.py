"""
Database connection module for Petrol Pump ERP.

Handles SQLAlchemy engine creation, session management,
and database connection pooling for offline operation.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Generator, Optional
import os

# Database URL - SQLite file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "petrol_pump.db")

# Create engine with WAL mode for better concurrency
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={
        "check_same_thread": False,
        "pool_pre_ping": True,
    }
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# Base class for declarative models
Base = declarative_base()


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


def get_connection() -> Generator:
    """
    Get a database connection for raw SQL queries.

    Usage:
        conn = next(get_connection())
    """
    return engine.connect()


if __name__ == "__main__":
    # Initialize the database
    init_db()
    print(f"Database initialized at: {DB_PATH}")
