"""Backup/restore service layer (CLAUDE.md: "backup before migrations",
"implement restore testing"). Wraps app/database/backup.py's pure file
operations with RBAC and audit logging, matching every other service in
the app. Restoring follows the same reason-required, audit-logged
pattern used for every other destructive-adjacent action - and takes
its own safety backup first, so a bad restore choice is itself
recoverable.
"""

from typing import List, Tuple

import os

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
    def check_integrity(self, actor_user_id: str) -> Tuple[bool, List[str]]:
        is_ok, messages = backup_module.run_integrity_check(self._db_path)
        # A pass and a failure get DIFFERENT event types rather than one
        # event whose description happens to read "ok". Anything wanting to
        # find past failures - the notification service does - would
        # otherwise have to pattern-match a human-readable string, which
        # silently stops working the first time that wording changes.
        self._audit_repo.record(
            event_type="database_integrity_checked" if is_ok else "database_integrity_failed",
            actor_id=actor_user_id,
            entity_type="Database",
            description="ok" if is_ok else "; ".join(messages),
        )
        return is_ok, messages

    @require_permission(Permission.BACKUP_MANAGE.value)
    def copy_backup_offsite(self, actor_user_id: str, backup_path: str, destination_dir: str) -> str:
        """Copy a backup somewhere that is not this disk.

        Audit-logged both ways: an off-device copy is a copy of every
        financial record in the business leaving the machine, which is a
        security-relevant event in its own right, not just a safety one.
        """
        if not destination_dir or not destination_dir.strip():
            raise ValueError("A destination folder is required")
        try:
            destination = backup_module.copy_backup_to(backup_path, destination_dir.strip())
        except (OSError, IOError) as exc:
            self._audit_repo.record(
                event_type="backup_offsite_copy_failed",
                actor_id=actor_user_id,
                entity_type="Backup",
                description=f"{backup_path} -> {destination_dir}: {exc}",
            )
            raise
        self._audit_repo.record(
            event_type="backup_copied_offsite",
            actor_id=actor_user_id,
            entity_type="Backup",
            description=f"{os.path.basename(backup_path)} -> {destination_dir}",
        )
        return destination

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
