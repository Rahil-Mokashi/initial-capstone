"""Backup/restore UI (CLAUDE.md: "backup before migrations", "implement
restore testing"). Presentation only - BackupService owns the RBAC,
audit logging, and the safety backup taken before any restore.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from app.core.exceptions import AppError
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
    def __init__(self, backup_service, actor_user_id: str):
        super().__init__()
        self._backup_service = backup_service
        self._actor_user_id = actor_user_id

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

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
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
        layout.addWidget(self.table)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh()

    def refresh(self) -> None:
        backups = self._backup_service.list_backups(self._actor_user_id)
        self.table.setRowCount(len(backups))
        for row_index, info in enumerate(backups):
            self.table.setItem(row_index, 0, QTableWidgetItem(info.created_at.strftime("%Y-%m-%d %H:%M:%S")))
            self.table.setItem(row_index, 1, QTableWidgetItem(info.filename))
            self.table.setItem(row_index, 2, QTableWidgetItem(_format_size(info.size_bytes)))
            self.table.item(row_index, 0).setData(Qt.UserRole, info.path)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _backup_now(self) -> None:
        try:
            self._backup_service.create_backup(self._actor_user_id)
        except AppError as exc:
            QMessageBox.warning(self, "Could not create backup", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not create backup", describe_unexpected_error(exc))
            return
        self.refresh()
        QMessageBox.information(self, "Backup created", "A new backup has been saved.")

    def _check_integrity(self) -> None:
        try:
            is_ok, messages = self._backup_service.check_integrity(self._actor_user_id)
        except AppError as exc:
            QMessageBox.warning(self, "Could not check integrity", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not check integrity", describe_unexpected_error(exc))
            return

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
