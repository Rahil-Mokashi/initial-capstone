"""Audit log viewer (CLAUDE.md: "Implement audit logging for all
changes"). Every service already writes to AuditLog at the point of the
action - this is purely a read-only screen for AUDIT_VIEW-holding roles
to actually see that trail, which previously had no UI anywhere.
"""

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.qt_utils import qdate_to_date

TABLE_HEADERS = ["When", "Event", "Actor", "Entity", "Description"]


class AuditLogWindow(QMainWindow):
    def __init__(self, audit_service, user_repo, actor_user_id: str):
        super().__init__()
        self._audit_service = audit_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Audit Log")
        self.setMinimumSize(920, 600)

        title = QLabel("Audit Log")
        title.setObjectName("title")

        self.event_type_input = QLineEdit()
        self.event_type_input.setPlaceholderText("Event contains...")
        self.event_type_input.returnPressed.connect(self.refresh)

        self.actor_combo = QComboBox()
        self.actor_combo.addItem("All users", None)
        for user in user_repo.list_all():
            self.actor_combo.addItem(user.username, user.id)

        self.date_from_input = QDateEdit(QDate.currentDate().addDays(-7))
        self.date_from_input.setCalendarPopup(True)
        self.date_to_input = QDateEdit(QDate.currentDate())
        self.date_to_input.setCalendarPopup(True)

        self.filter_button = QPushButton("Filter")
        self.filter_button.setCursor(Qt.PointingHandCursor)
        self.filter_button.clicked.connect(self.refresh)

        filter_row = QHBoxLayout()
        filter_row.addWidget(self.event_type_input)
        filter_row.addWidget(self.actor_combo)
        filter_row.addWidget(QLabel("From"))
        filter_row.addWidget(self.date_from_input)
        filter_row.addWidget(QLabel("To"))
        filter_row.addWidget(self.date_to_input)
        filter_row.addWidget(self.filter_button)

        self.table = QTableWidget(0, len(TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(TABLE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addLayout(filter_row)
        layout.addWidget(self.table)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh()

    def refresh(self) -> None:
        entries = self._audit_service.search(
            self._actor_user_id,
            event_type=self.event_type_input.text().strip() or None,
            filter_actor_id=self.actor_combo.currentData(),
            date_from=qdate_to_date(self.date_from_input.date()),
            date_to=qdate_to_date(self.date_to_input.date()),
        )

        self.table.setRowCount(len(entries))
        for row_index, entry in enumerate(entries):
            self.table.setItem(row_index, 0, QTableWidgetItem(entry.created_at.strftime("%Y-%m-%d %H:%M:%S")))
            self.table.setItem(row_index, 1, QTableWidgetItem(entry.event_type))
            self.table.setItem(row_index, 2, QTableWidgetItem(entry.actor.username if entry.actor else ""))
            entity = f"{entry.entity_type} {entry.entity_id}" if entry.entity_type else ""
            self.table.setItem(row_index, 3, QTableWidgetItem(entity))
            self.table.setItem(row_index, 4, QTableWidgetItem(entry.description or ""))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
