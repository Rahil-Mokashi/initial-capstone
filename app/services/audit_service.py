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
    def verify_trail(self, actor_user_id: str) -> tuple[bool, list[str]]:
        """Recompute the audit hash chain and report whether it is intact.

        Answers the question an auditor actually asks: has this trail been
        altered since it was written? A break means the database was
        modified outside the application, and names roughly where.

        The verification itself is audit-logged - including when it fails,
        which is precisely when someone would most want it not to be.
        """
        is_intact, problems = self._audit_repo.verify_chain()
        # Distinct event types for pass and fail, for the same reason as
        # BackupService.check_integrity: a detected break in the audit
        # chain is the single most serious thing this application can
        # discover about itself, and finding it later must not depend on
        # pattern-matching the word "intact" out of a description.
        self._audit_repo.record(
            event_type="audit_trail_verified" if is_intact else "audit_trail_tampered",
            actor_id=actor_user_id,
            entity_type="AuditLog",
            description="intact" if is_intact else f"{len(problems)} problem(s): " + "; ".join(problems[:5]),
        )
        return is_intact, problems

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
