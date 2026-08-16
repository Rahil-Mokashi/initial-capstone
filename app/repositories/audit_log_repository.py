from datetime import date, datetime, time, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
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
        self._session.add(entry)
        safe_commit(self._session)
        self._session.refresh(entry)
        return entry

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
