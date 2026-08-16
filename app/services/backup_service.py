"""Backup/restore service layer (CLAUDE.md: "backup before migrations",
"implement restore testing"). Wraps app/database/backup.py's pure file
operations with RBAC and audit logging, matching every other service in
the app. Restoring follows the same reason-required, audit-logged
pattern used for every other destructive-adjacent action - and takes
its own safety backup first, so a bad restore choice is itself
recoverable.
"""

from typing import List

from app.core.constants import Permission
from app.core.permissions import require_permission
from app.database import backup as backup_module


class BackupService:
    def __init__(self, db_path: str, audit_repo, auth_service):
        self._db_path = db_path
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    @require_permission(Permission.BACKUP_MANAGE.value)
    def create_backup(self, actor_user_id: str) -> backup_module.BackupInfo:
        backup_path = backup_module.create_backup(self._db_path, reason="manual")
        self._audit_repo.record(
            event_type="backup_created",
            actor_id=actor_user_id,
            entity_type="Database",
            description=f"Manual backup created at {backup_path}",
        )
        return self._find_backup(backup_path)

    @require_permission(Permission.BACKUP_MANAGE.value)
    def list_backups(self, actor_user_id: str) -> List[backup_module.BackupInfo]:
        return backup_module.list_backups(self._db_path)

    @require_permission(Permission.BACKUP_MANAGE.value)
    def restore_backup(self, actor_user_id: str, backup_path: str, reason: str) -> None:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to restore from a backup")

        backup_module.create_backup(self._db_path, reason="pre_restore")
        backup_module.restore_backup(backup_path, self._db_path)
        self._audit_repo.record(
            event_type="database_restored",
            actor_id=actor_user_id,
            entity_type="Database",
            description=reason.strip(),
            old_value=self._db_path,
            new_value=backup_path,
        )

    def _find_backup(self, backup_path: str) -> backup_module.BackupInfo:
        for info in backup_module.list_backups(self._db_path):
            if info.path == backup_path:
                return info
        raise FileNotFoundError(backup_path)
