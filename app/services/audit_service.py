"""Read-only access to the audit trail (problemstatement.md #40).

AuditLogRepository has no update/delete methods and this service adds
nothing that writes - every other service already records its own audit
events directly through the repository at the point of the action. This
exists purely so AUDIT_VIEW is actually enforced somewhere: the
permission has been defined and granted to Manager/Accountant/Admin/
Owner since Phase 4, but nothing ever checked it because there was no
screen to view the trail on until now.
"""

from datetime import date
from typing import List, Optional

from app.core.constants import Permission
from app.core.permissions import require_permission
from app.models.audit_log import AuditLog


class AuditService:
    def __init__(self, audit_repo, auth_service):
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    @require_permission(Permission.AUDIT_VIEW.value)
    def search(
        self,
        actor_user_id: str,
        event_type: Optional[str] = None,
        filter_actor_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> List[AuditLog]:
        return self._audit_repo.search(
            event_type=event_type, actor_id=filter_actor_id, date_from=date_from, date_to=date_to
        )
