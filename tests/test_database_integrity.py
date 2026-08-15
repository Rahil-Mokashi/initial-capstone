"""
Database integrity tests (problemstatement.md #45: "Test database
integrity"). These verify the foundations every other service relies on:
SQLite foreign-key enforcement is actually turned on, WAL mode is enabled,
and a failed write leaves the session usable for the next operation
instead of poisoning it.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import app.database.connection  # noqa: F401  (registers the FK/WAL PRAGMA event listener on Engine)
import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.models.role import Role
from app.repositories.base import safe_commit
from app.models.employee import Employee


@pytest.fixture()
def db_session(tmp_path):
    sqlite_path = str(tmp_path / "test_integrity.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    session = session_factory()
    yield session
    session.close()


def test_wal_mode_is_enabled(db_session):
    mode = db_session.execute(text("PRAGMA journal_mode")).scalar()
    assert mode.lower() == "wal"


def test_foreign_keys_pragma_is_on(db_session):
    value = db_session.execute(text("PRAGMA foreign_keys")).scalar()
    assert value == 1


def test_foreign_key_violation_is_rejected(db_session):
    """An Employee row referencing a non-existent role_id must be rejected
    by the database itself, not just by service-layer pre-checks."""
    bad_employee = Employee(
        employee_code="EMP-9999",
        first_name="Ghost",
        last_name="Employee",
        contact_number="0000000000",
        joining_date=date(2026, 1, 1),
        role_id="this-role-does-not-exist",
    )
    db_session.add(bad_employee)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_session_recovers_after_failed_commit_via_safe_commit(db_session):
    """After safe_commit rolls back a failed write, the same session must
    still be usable for a subsequent, valid write — this is the whole
    point of routing every repository write through safe_commit."""
    role_a = Role(id="role-a", name="DUPLICATE_NAME")
    db_session.add(role_a)
    safe_commit(db_session)

    role_b = Role(id="role-b", name="DUPLICATE_NAME")  # violates unique constraint on name
    db_session.add(role_b)
    with pytest.raises(SQLAlchemyError):
        safe_commit(db_session)

    # The session must not be left in an aborted-transaction state.
    role_c = Role(id="role-c", name="A_DIFFERENT_NAME")
    db_session.add(role_c)
    safe_commit(db_session)  # would raise "transaction is inactive" if rollback hadn't happened

    assert db_session.query(Role).filter_by(name="A_DIFFERENT_NAME").first() is not None
    assert db_session.query(Role).filter_by(id="role-b").first() is None


@pytest.mark.filterwarnings("ignore:Session's state has been changed on a non-active transaction")
def test_session_without_safe_commit_would_stay_broken(db_session):
    """Documents the failure mode safe_commit exists to prevent: calling
    session.commit() directly on a failed write leaves the session's
    transaction aborted until an explicit rollback."""
    role_a = Role(id="role-x", name="ANOTHER_DUPLICATE")
    db_session.add(role_a)
    db_session.commit()

    role_b = Role(id="role-y", name="ANOTHER_DUPLICATE")
    db_session.add(role_b)
    with pytest.raises(SQLAlchemyError):
        db_session.commit()  # deliberately not using safe_commit here

    role_c = Role(id="role-z", name="YET_ANOTHER_NAME")
    db_session.add(role_c)
    with pytest.raises(SQLAlchemyError):
        db_session.commit()  # fails too, because the session was never rolled back

    db_session.rollback()  # manual cleanup so the fixture teardown doesn't also fail
