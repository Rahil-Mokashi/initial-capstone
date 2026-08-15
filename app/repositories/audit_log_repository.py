from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


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
        self._session.commit()
        self._session.refresh(entry)
        return entry

    def list_for_actor(self, actor_id: str):
        return (
            self._session.query(AuditLog)
            .filter_by(actor_id=actor_id)
            .order_by(AuditLog.created_at.desc())
            .all()
        )
