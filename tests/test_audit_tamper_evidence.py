"""The audit trail is append-only in fact, not only by convention.

Nothing in the application updates or deletes an audit row, but the .db
file sits on a forecourt PC and anyone with a DB browser could rewrite the
trail - and until now, nobody could tell.

Two layers, and the distinction between them matters:

  * Database TRIGGERS reject UPDATE and DELETE outright, so even direct
    SQL fails. This is tamper-RESISTANT.
  * A HASH CHAIN means each row commits to the whole history before it, so
    altering or removing a row breaks every hash after it. This is
    tamper-EVIDENT.

Both are needed. Triggers can be dropped by anyone who can also run DDL;
the chain is what detects it when they do. Truly preventing modification
would need append-only storage the operator does not control, which an
offline desktop app does not have - so being precise about what is
achievable is part of the design.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

import app.database.connection  # noqa: F401
import app.models  # noqa: F401
from app.database.base import Base
from app.repositories.audit_log_repository import AuditLogRepository, compute_entry_hash


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = factory()
    # create_all does not run migrations, so add the triggers the same way
    # the migration does.
    for name, action in (("no_update", "UPDATE"), ("no_delete", "DELETE")):
        session.execute(text(
            f"CREATE TRIGGER audit_logs_{name} BEFORE {action} ON audit_logs "
            f"BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;"))
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def repo(db):
    return AuditLogRepository(db)


# ---------------------------------------------------------------------
# Tamper resistance: the triggers
# ---------------------------------------------------------------------

def test_an_audit_entry_cannot_be_updated_even_by_raw_sql(db, repo):
    repo.record(event_type="login_success", description="original")
    with pytest.raises((IntegrityError, OperationalError)):
        db.execute(text("UPDATE audit_logs SET description = 'tampered'"))
        db.commit()


def test_an_audit_entry_cannot_be_deleted_even_by_raw_sql(db, repo):
    repo.record(event_type="sale_recorded")
    with pytest.raises((IntegrityError, OperationalError)):
        db.execute(text("DELETE FROM audit_logs"))
        db.commit()


# ---------------------------------------------------------------------
# Tamper evidence: the hash chain
# ---------------------------------------------------------------------

def test_entries_are_chained_to_their_predecessor(db, repo):
    first = repo.record(event_type="login_success")
    second = repo.record(event_type="sale_recorded")
    third = repo.record(event_type="logout")

    assert first.previous_hash is None, "the first entry has no predecessor"
    assert second.previous_hash == first.entry_hash
    assert third.previous_hash == second.entry_hash
    assert len({first.entry_hash, second.entry_hash, third.entry_hash}) == 3


def test_an_untouched_chain_verifies(db, repo):
    for event in ("login_success", "sale_recorded", "sale_cancelled", "logout"):
        repo.record(event_type=event)
    intact, problems = repo.verify_chain()
    assert intact is True, problems


def test_modifying_an_entry_breaks_verification(db, repo):
    """The whole point: a change made outside the application is found."""
    repo.record(event_type="login_success")
    target = repo.record(event_type="sale_recorded", description="Sold 10L for 1000")
    repo.record(event_type="logout")

    # Bypass the triggers the way an attacker with the file would, by
    # dropping them first - which is exactly why the chain has to exist
    # as well as the triggers.
    db.execute(text("DROP TRIGGER audit_logs_no_update"))
    db.execute(text("UPDATE audit_logs SET description = 'Sold 1L for 100' WHERE id = :i"),
               {"i": target.id})
    db.commit()
    db.expire_all()

    intact, problems = repo.verify_chain()
    assert intact is False
    assert any("modified" in p for p in problems)


def test_deleting_an_entry_breaks_verification(db, repo):
    """Removing an inconvenient row is the likeliest tampering of all."""
    repo.record(event_type="login_success")
    target = repo.record(event_type="permission_denied")
    repo.record(event_type="logout")

    db.execute(text("DROP TRIGGER audit_logs_no_delete"))
    db.execute(text("DELETE FROM audit_logs WHERE id = :i"), {"i": target.id})
    db.commit()
    db.expire_all()

    intact, problems = repo.verify_chain()
    assert intact is False
    assert any("does not follow its predecessor" in p for p in problems)


def test_the_hash_covers_every_meaningful_field(db, repo):
    """A field left out of the hash is a field an attacker can change
    without detection."""
    entry = repo.record(
        event_type="sale_cancelled", actor_id=None, entity_type="Sale",
        entity_id="abc", description="reason", old_value="completed",
        new_value="cancelled", device_info="PC-1")
    baseline = compute_entry_hash(entry)

    for field, value in [
        ("event_type", "login_success"), ("entity_type", "Payment"),
        ("entity_id", "xyz"), ("description", "different"),
        ("old_value", "x"), ("new_value", "y"), ("device_info", "PC-2"),
    ]:
        original = getattr(entry, field)
        setattr(entry, field, value)
        assert compute_entry_hash(entry) != baseline, f"{field} is not covered by the hash"
        setattr(entry, field, original)


def test_rows_predating_the_chain_are_not_treated_as_tampering(db, repo):
    """Existing installations have audit rows written before this feature.
    They are unverifiable, not suspicious, and must not raise a false alarm."""
    db.execute(text(
        "INSERT INTO audit_logs (id, event_type, created_at, previous_hash, entry_hash) "
        "VALUES ('legacy-1', 'login_success', '2026-01-01 00:00:00.000000', NULL, NULL)"))
    db.commit()
    repo.record(event_type="sale_recorded")

    intact, problems = repo.verify_chain()
    assert intact is True, problems
