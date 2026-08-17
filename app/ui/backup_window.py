"""Backup/restore UI (CLAUDE.md: "backup before migrations", "implement
restore testing"). Presentation only - BackupService owns the RBAC,
audit logging, and the safety backup taken before any restore.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import OFFSITE_BACKUP_STALE_AFTER_DAYS
from app.core.exceptions import AppError
from app.database import backup as backup_module
from app.ui.background import run_in_background
from app.ui.qt_utils import describe_unexpected_error

BACKUP_HEADERS = ["Created", "File", "Size"]


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class BackupWindow(QMainWindow):
    def __init__(self, backup_service, actor_user_id: str, settings_service=None):
        super().__init__()
        self._backup_service = backup_service
        self._actor_user_id = actor_user_id
        # Optional so existing callers and tests keep working. When present,
        # the off-device folder configured in Settings is used as the default
        # destination and as the folder the staleness warning watches -
        # otherwise the operator has to re-find the USB drive every time,
        # and that friction is exactly what stops off-device backups
        # actually happening.
        self._settings_service = settings_service

        self.setWindowTitle("Backups")
        self.setMinimumSize(720, 520)

        title = QLabel("Database Backups")
        title.setObjectName("title")

        subtitle = QLabel(
            "A backup is taken automatically before any schema update. "
            "You can also take one manually, or restore an earlier one."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        self.backup_now_button = QPushButton("Back Up Now")
        self.backup_now_button.setCursor(Qt.PointingHandCursor)
        self.backup_now_button.clicked.connect(self._backup_now)

        self.restore_button = QPushButton("Restore Selected")
        self.restore_button.setObjectName("dangerButton")
        self.restore_button.clicked.connect(self._restore_selected)

        self.check_integrity_button = QPushButton("Check Integrity")
        self.check_integrity_button.setObjectName("secondaryButton")
        self.check_integrity_button.clicked.connect(self._check_integrity)

        self.copy_offsite_button = QPushButton("Copy to USB / Network...")
        self.copy_offsite_button.setObjectName("secondaryButton")
        self.copy_offsite_button.setToolTip(
            "Copy the selected backup somewhere that is not this disk. Every "
            "backup here sits on the same drive as the database, so a dead "
            "drive, a theft or ransomware would take both.")
        self.copy_offsite_button.clicked.connect(self._copy_offsite)

        # A warning, not an alarm - the same non-accusatory tone as
        # reconciliation variance. It reports a real exposure without
        # implying the operator has done something wrong.
        self.offsite_warning = QLabel("")
        self.offsite_warning.setObjectName("warningLabel")
        self.offsite_warning.setWordWrap(True)
        self.offsite_warning.hide()

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(self.copy_offsite_button)
        top_row.addWidget(self.check_integrity_button)
        top_row.addWidget(self.restore_button)
        top_row.addWidget(self.backup_now_button)

        self.table = QTableWidget(0, len(BACKUP_HEADERS))
        self.table.setHorizontalHeaderLabels(BACKUP_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(top_row)
        layout.addWidget(subtitle)
        layout.addWidget(self.offsite_warning)
        layout.addWidget(self.table)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh()

    def refresh(self) -> None:
        self._refresh_offsite_warning()
        backups = self._backup_service.list_backups(self._actor_user_id)
        self.table.setRowCount(len(backups))
        for row_index, info in enumerate(backups):
            self.table.setItem(row_index, 0, QTableWidgetItem(info.created_at.strftime("%Y-%m-%d %H:%M:%S")))
            self.table.setItem(row_index, 1, QTableWidgetItem(info.filename))
            self.table.setItem(row_index, 2, QTableWidgetItem(_format_size(info.size_bytes)))
            self.table.item(row_index, 0).setData(Qt.UserRole, info.path)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _action_buttons(self):
        """Disabled while a background task runs, so a slow backup cannot
        be started four times by an impatient click."""
        return [b for b in (
            getattr(self, "backup_now_button", None),
            getattr(self, "restore_button", None),
            getattr(self, "copy_offsite_button", None),
            getattr(self, "check_integrity_button", None),
        ) if b is not None]

    def _report(self, exc: Exception, title: str) -> None:
        """Errors arrive here on the GUI thread via a queued signal, so
        showing a dialog is safe."""
        message = str(exc) if isinstance(exc, AppError) else describe_unexpected_error(exc)
        QMessageBox.warning(self, title, message)

    def _copy_offsite(self) -> None:
        """Copy the selected backup off this machine.

        This is the single largest data-loss exposure in the product:
        every backup lands next to the database, which protects against
        software failure and not at all against a dead drive, a theft, a
        fire or ransomware. With no cloud replica by design, an off-device
        copy is the only real protection there is.
        """
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(
                self, "Copy backup", "Select a backup to copy first.")
            return
        backup_path = self.table.item(rows[0].row(), 0).data(Qt.UserRole)

        destination = QFileDialog.getExistingDirectory(
            self, "Choose a USB drive or network folder",
            self._configured_offsite_dir() or "")
        if not destination:
            return

        run_in_background(
            self,
            lambda: self._backup_service.copy_backup_offsite(
                self._actor_user_id, backup_path, destination),
            on_done=self._on_offsite_copied,
            on_error=lambda exc: self._report(exc, "Could not copy the backup"),
            busy_widgets=self._action_buttons(),
        )

    def _on_offsite_copied(self, destination) -> None:
        self._last_offsite_dir = os.path.dirname(str(destination))
        self._refresh_offsite_warning()
        QMessageBox.information(
            self, "Backup copied",
            f"The backup was copied and verified at:\n\n{destination}")

    def _configured_offsite_dir(self):
        """The folder set on the Settings screen, if there is one.

        Failures here are swallowed deliberately: a missing settings row or
        a permission problem must not stop the Backups screen from opening,
        because taking a backup is more important than defaulting a path.
        """
        if self._settings_service is None:
            return None
        try:
            return self._settings_service.get_company_profile().offsite_backup_dir
        except Exception:  # noqa: BLE001
            return None

    def _refresh_offsite_warning(self) -> None:
        """Nag when the newest off-device copy is stale, or when there has
        never been one.

        Deliberately a nag rather than a scheduler: a pump has no IT staff
        and the machine is not guaranteed to be running at any particular
        time, so a visible warning beats a background job that silently
        never fires.
        """
        destination = getattr(self, "_last_offsite_dir", None) or self._configured_offsite_dir()
        if not destination:
            self.offsite_warning.setText(
                "No off-device backup has been made from this screen yet. "
                "Every backup listed below is on the same drive as the database.")
            self.offsite_warning.show()
            return

        age_days = backup_module.latest_offsite_copy_age_days(destination)
        if age_days is None:
            self.offsite_warning.setText(
                f"The off-device location ({destination}) is not reachable right now.")
            self.offsite_warning.show()
        elif age_days > OFFSITE_BACKUP_STALE_AFTER_DAYS:
            self.offsite_warning.setText(
                f"The most recent off-device backup is {age_days:.0f} days old. "
                "Copy a fresh one to a USB drive or network folder.")
            self.offsite_warning.show()
        else:
            self.offsite_warning.hide()

    def _backup_now(self) -> None:
        """Runs off the GUI thread (problemstatement.md #44).

        create_backup copies the whole database page by page through
        SQLite's online backup API and then verifies the result with a
        full PRAGMA integrity_check. On a database with a few years of
        trading that is seconds, and every one of them would be a frozen,
        "Not Responding" window if it ran in this slot.
        """
        run_in_background(
            self,
            lambda: self._backup_service.create_backup(self._actor_user_id),
            on_done=self._on_backup_created,
            on_error=lambda exc: self._report(exc, "Could not create backup"),
            busy_widgets=self._action_buttons(),
        )

    def _on_backup_created(self, _result) -> None:
        self.refresh()
        QMessageBox.information(self, "Backup created", "A new backup has been saved.")

    def _check_integrity(self) -> None:
        """PRAGMA integrity_check walks every B-tree page and index entry
        in the file, so it is the slowest read the app ever performs."""
        run_in_background(
            self,
            lambda: self._backup_service.check_integrity(self._actor_user_id),
            on_done=lambda result: self._on_integrity_checked(*result),
            on_error=lambda exc: self._report(exc, "Could not check integrity"),
            busy_widgets=self._action_buttons(),
        )

    def _on_integrity_checked(self, is_ok, messages) -> None:
        if is_ok:
            QMessageBox.information(self, "Integrity check", "The database passed its integrity check.")
        else:
            QMessageBox.warning(self, "Integrity check", "Problems were found:\n\n" + "\n".join(messages))

    def _restore_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Restore", "Select a backup to restore first.")
            return
        backup_path = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        filename = self.table.item(rows[0].row(), 1).text()

        confirmation = QMessageBox.warning(
            self,
            "Restore database",
            f"This replaces the current database with {filename}.\n\n"
            "The current data will be backed up first, but you must restart "
            "the application afterward for the restored data to take effect.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirmation != QMessageBox.Yes:
            return

        reason, ok = QInputDialog.getText(self, "Restore database", "Reason:")
        if not ok or not reason.strip():
            return

        try:
            self._backup_service.restore_backup(self._actor_user_id, backup_path, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not restore backup", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not restore backup", describe_unexpected_error(exc))
            return

        self.refresh()
        QMessageBox.information(
            self, "Restore complete", "The database has been restored. Please close and restart the application."
        )
