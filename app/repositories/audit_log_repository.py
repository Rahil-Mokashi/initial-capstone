from datetime import date, datetime, time, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import hashlib
import uuid
from datetime import datetime, timezone

from app.models.audit_log import AuditLog


def compute_entry_hash(entry: AuditLog) -> str:
    """SHA-256 over an entry's own fields plus its predecessor's hash.

    Every field that carries meaning is included, so changing any of them
    changes the hash. The previous hash is included too, which is what
    makes the entries a CHAIN rather than independent checksums: altering
    an old row invalidates every row after it, so tampering cannot be
    hidden by recomputing one hash.

    A plain fast SHA-256 is right here. Unlike a password there is no
    low-entropy secret to brute-force - the goal is detecting change, not
    resisting guessing.
    """
    parts = [
        entry.previous_hash or "",
        entry.id or "",
        entry.event_type or "",
        entry.actor_id or "",
        entry.entity_type or "",
        entry.entity_id or "",
        entry.description or "",
        entry.old_value or "",
        entry.new_value or "",
        entry.device_info or "",
        entry.created_at.isoformat() if entry.created_at else "",
    ]
    #  (unit separator) cannot appear in these values, so no field can
    # be crafted to look like a boundary and shift the others.
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()
from app.repositories.base import safe_commit


class AuditLogRepository:
    """Append-only access to the audit trail.

    Deliberately has no update/delete methods: audit records must never be
    changed or removed once written.
    """

    def __init__(self, session: Session):
        self._session = session

    def record(
        self,
        event_type: str,
        actor_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        description: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        device_info: Optional[str] = None,
    ) -> AuditLog:
        entry = AuditLog(
            event_type=event_type,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            old_value=old_value,
            new_value=new_value,
            device_info=device_info,
        )
        # Chain this entry to the one before it before writing, so the
        # trail is tamper-evident (see AuditLog's docstring).
        # id and created_at both come from Python-side column defaults that
        # SQLAlchemy applies at INSERT time, not at construction - so at
        # this point they are still None. They must be materialised BEFORE
        # hashing, or the row is written with an id and timestamp the hash
        # never covered, and verification fails on untampered data.
        entry.id = entry.id or str(uuid.uuid4())
        entry.created_at = entry.created_at or datetime.now(timezone.utc)
        previous = self.get_latest_entry()
        entry.previous_hash = previous.entry_hash if previous else None
        entry.entry_hash = compute_entry_hash(entry)

        self._session.add(entry)
        safe_commit(self._session)
        self._session.refresh(entry)
        return entry

    def get_latest_entry(self) -> Optional[AuditLog]:
        """The most recent entry, which the next one chains onto.

        Ordered by created_at then id: created_at alone is not a reliable
        tie-break because several audit rows written inside one service
        operation can share a timestamp, and a chain built on an ambiguous
        order would fail verification for no reason.
        """
        return (
            self._session.query(AuditLog)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .first()
        )

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Recompute every hash and confirm the chain is unbroken.

        Returns (is_intact, problems). A break tells you the audit trail
        was modified outside the application, and roughly where.
        """
        entries = (
            self._session.query(AuditLog)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        problems: list[str] = []
        expected_previous = None

        for entry in entries:
            if entry.entry_hash is None:
                # Rows written before the chain existed are not a tamper
                # signal; they simply predate it.
                expected_previous = None
                continue
            if entry.previous_hash != expected_previous:
                problems.append(
                    f"Entry {entry.id} ({entry.event_type}) does not follow its predecessor"
                )
            recomputed = compute_entry_hash(entry)
            if recomputed != entry.entry_hash:
                problems.append(
                    f"Entry {entry.id} ({entry.event_type}) has been modified since it was written"
                )
            expected_previous = entry.entry_hash

        return (not problems), problems

    def list_for_actor(self, actor_id: str):
        return (
            self._session.query(AuditLog)
            .filter_by(actor_id=actor_id)
            .order_by(AuditLog.created_at.desc())
            .all()
        )

    def search(
        self,
        event_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 500,
    ) -> List[AuditLog]:
        """date_from/date_to are local calendar dates, widened to the full
        local day and converted to UTC before comparing against
        created_at (stored UTC-aware) - see
        TankTransactionRepository.sum_for_tank_by_type for why a naive
        local-midnight boundary compared directly against a UTC
        timestamp silently drops rows whenever local time runs ahead of
        UTC."""
        query = self._session.query(AuditLog)
        if event_type:
            query = query.filter(AuditLog.event_type.ilike(f"%{event_type}%"))
        if actor_id:
            query = query.filter_by(actor_id=actor_id)
        if date_from:
            start_of_day = datetime.combine(date_from, time.min).astimezone(timezone.utc)
            query = query.filter(AuditLog.created_at >= start_of_day)
        if date_to:
            end_of_day = datetime.combine(date_to, time.max).astimezone(timezone.utc)
            query = query.filter(AuditLog.created_at <= end_of_day)
        return query.order_by(AuditLog.created_at.desc()).limit(limit).all()
