"""Every datetime read from the database is timezone-aware UTC.

SQLite has no native datetime type, so SQLAlchemy stores a DateTime as an
ISO-8601 string, and a string carries no offset. The value written is the
correct UTC instant; the tzinfo label saying so is what was lost. Every
value therefore came back NAIVE, and comparing a naive datetime with the
aware `datetime.now(timezone.utc)` the rest of this app correctly uses
raises TypeError - or, when both happen to be naive, silently compares a
local wall-clock reading against a UTC one.

That is not theoretical here. It is exactly how the shipped
fuel-reconciliation bug happened: on this IST (UTC+5:30) machine a naive
local day boundary compared against UTC-stored transaction timestamps
silently dropped every transaction recorded between local midnight and
05:30 UTC. It was fixed at two call sites and worked around at a third,
while the trap stayed armed everywhere else - because it lived in the
column type, not in any particular query.

app/database/types.py's UtcDateTime disarms it structurally.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.database.connection  # noqa: F401  (installs the FK/WAL pragma listener)
import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.user_session import UserSession


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_utc.db'}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = factory()
    yield session
    session.close()


def test_a_stored_datetime_comes_back_timezone_aware(db_session):
    db_session.add(AuditLog(event_type="test"))
    db_session.commit()
    db_session.expire_all()

    created = db_session.query(AuditLog).first().created_at
    assert created.tzinfo is not None, "datetime came back naive"
    assert created.utcoffset() == timedelta(0), "datetime is not UTC"


def test_a_stored_datetime_compares_with_an_aware_now_without_raising(db_session):
    """The comparison that used to raise TypeError all over the app."""
    db_session.add(AuditLog(event_type="test"))
    db_session.commit()
    db_session.expire_all()

    created = db_session.query(AuditLog).first().created_at
    assert created <= datetime.now(timezone.utc)  # would have been a TypeError


def test_an_aware_value_written_in_a_non_utc_zone_is_normalised(db_session):
    """A caller passing IST must not store a local wall-clock reading."""
    ist = timezone(timedelta(hours=5, minutes=30))
    moment = datetime(2026, 8, 17, 10, 30, 0, tzinfo=ist)  # 05:00 UTC

    # A real user row: foreign keys are genuinely enforced in this app
    # (PRAGMA foreign_keys=ON, installed on every connection), so a
    # placeholder id is correctly rejected.
    user = User(username="tz_user", email="tz@example.com", password_hash="x", is_active=True)
    db_session.add(user)
    db_session.commit()

    db_session.add(UserSession(
        user_id=user.id, token_hash="h", expires_at=moment, is_active=True,
    ))
    db_session.commit()
    db_session.expire_all()

    stored = db_session.query(UserSession).first().expires_at
    assert stored == moment                      # same instant
    assert stored.hour == 5 and stored.minute == 0  # expressed in UTC


def test_the_on_disk_format_is_unchanged_so_no_migration_is_needed(db_session):
    """Existing databases in the field must keep working untouched.

    UtcDateTime stores naive UTC, byte-identical to what every previous
    version of this app wrote - it only re-attaches the label on read. If
    this ever changes, every deployed database needs a data migration.
    """
    db_session.add(AuditLog(event_type="test"))
    db_session.commit()

    raw = db_session.execute(text("SELECT created_at FROM audit_logs LIMIT 1")).scalar()
    assert "+" not in str(raw), "an offset leaked into storage; the format changed"


def test_a_naive_legacy_row_is_read_back_as_utc(db_session):
    """Rows written before this type existed are naive UTC on disk and
    must be interpreted as UTC, not as local time."""
    db_session.add(AuditLog(event_type="legacy"))
    db_session.commit()
    db_session.execute(text(
        "UPDATE audit_logs SET created_at = '2026-01-01 12:00:00.000000'"
    ))
    db_session.commit()
    db_session.expire_all()

    created = db_session.query(AuditLog).first().created_at
    assert created == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
