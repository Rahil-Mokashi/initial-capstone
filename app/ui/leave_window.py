"""Leave Management UI (client-perspective review, 2026-09-23).

Request + approve/reject/cancel, the same shape as ExpenseWindow's own
approve/reject flow - deliberately no leave-balance/entitlement UI, since
LeaveService itself doesn't track one (see its module docstring).
"""

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.constants import Permission
from app.core.exceptions import AppError
from app.schemas.leave_request import LeaveRequestCreate
from app.ui.base_window import PageWindow
from app.ui.qt_utils import describe_unexpected_error

HEADERS = ["Employee", "From", "To", "Reason", "Status", "Decided By"]


class LeaveWindow(PageWindow):
    def __init__(self, leave_service, employee_service, auth_service, actor_user_id: str):
        super().__init__()
        self._leave_service = leave_service
        self._employee_service = employee_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Leave")
        self.setMinimumSize(860, 600)

        title = QLabel("Leave")
        title.setObjectName("title")

        can_manage = auth_service.check_permission(actor_user_id, Permission.LEAVE_MANAGE.value)
        can_approve = auth_service.check_permission(actor_user_id, Permission.LEAVE_APPROVE.value)

        self.request_button = QPushButton("+ Request Leave")
        self.request_button.setCursor(Qt.PointingHandCursor)
        self.request_button.clicked.connect(self._open_request_dialog)

        self.approve_button = QPushButton("Approve Selected")
        self.approve_button.setObjectName("secondaryButton")
        self.approve_button.clicked.connect(self._approve_selected)

        self.reject_button = QPushButton("Reject Selected")
        self.reject_button.setObjectName("dangerButton")
        self.reject_button.clicked.connect(self._reject_selected)

        self.cancel_button = QPushButton("Cancel Selected")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.clicked.connect(self._cancel_selected)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.cancel_button)
        top_row.addWidget(self.reject_button)
        top_row.addWidget(self.approve_button)
        top_row.addWidget(self.request_button)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addLayout(top_row)
        layout.addWidget(self.table)

        self._build_page(layout)

        # Deferred until every button above is actually parented - i.e.
        # until AFTER _build_page installs this layout onto self (2026-
        # 09-16, user-reported flicker) - see app/ui/sales_window.py's
        # SalesTab.__init__ for the full explanation. Calling setVisible
        # any earlier, before that installation, briefly makes each
        # button its own independent top-level OS window.
        self.request_button.setVisible(can_manage)
        self.approve_button.setVisible(can_approve)
        self.reject_button.setVisible(can_approve)
        self.cancel_button.setVisible(can_manage)

        self.refresh()

    def refresh(self) -> None:
        requests = self._leave_service.list_leave_requests(self._actor_user_id)
        self.table.setRowCount(len(requests))
        for row_index, leave_request in enumerate(requests):
            employee = leave_request.employee
            employee_name = f"{employee.first_name} {employee.last_name}" if employee else ""
            self.table.setItem(row_index, 0, QTableWidgetItem(employee_name))
            self.table.setItem(row_index, 1, QTableWidgetItem(leave_request.date_from.strftime("%Y-%m-%d")))
            self.table.setItem(row_index, 2, QTableWidgetItem(leave_request.date_to.strftime("%Y-%m-%d")))
            self.table.setItem(row_index, 3, QTableWidgetItem(leave_request.reason))
            self.table.setItem(row_index, 4, QTableWidgetItem(leave_request.status.title()))
            decided_by = leave_request.decided_by
            decided_by_name = f"{decided_by.username}" if decided_by else ""
            self.table.setItem(row_index, 5, QTableWidgetItem(decided_by_name))
            self.table.item(row_index, 0).setData(Qt.UserRole, leave_request.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_request_dialog(self) -> None:
        dialog = LeaveRequestFormDialog(self._leave_service, self._employee_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _selected_leave_request_id(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def _approve_selected(self) -> None:
        leave_request_id = self._selected_leave_request_id()
        if not leave_request_id:
            QMessageBox.information(self, "Approve leave", "Select a leave request to approve first.")
            return
        remarks, ok = QInputDialog.getText(self, "Approve leave", "Remarks (optional):")
        if not ok:
            return
        try:
            self._leave_service.approve_leave_request(self._actor_user_id, leave_request_id, remarks.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not approve leave", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not approve leave", describe_unexpected_error(exc))
        self.refresh()

    def _reject_selected(self) -> None:
        leave_request_id = self._selected_leave_request_id()
        if not leave_request_id:
            QMessageBox.information(self, "Reject leave", "Select a leave request to reject first.")
            return
        reason, ok = QInputDialog.getText(self, "Reject leave", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._leave_service.reject_leave_request(self._actor_user_id, leave_request_id, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not reject leave", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not reject leave", describe_unexpected_error(exc))
        self.refresh()

    def _cancel_selected(self) -> None:
        leave_request_id = self._selected_leave_request_id()
        if not leave_request_id:
            QMessageBox.information(self, "Cancel leave", "Select a leave request to cancel first.")
            return
        reason, ok = QInputDialog.getText(self, "Cancel leave request", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._leave_service.cancel_leave_request(self._actor_user_id, leave_request_id, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not cancel leave request", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not cancel leave request", describe_unexpected_error(exc))
        self.refresh()


class LeaveRequestFormDialog(QDialog):
    def __init__(self, leave_service, employee_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._leave_service = leave_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Request Leave")
        self.setMinimumWidth(400)

        self.employee_combo = QComboBox()
        for employee in employee_service.list_employees(actor_user_id):
            self.employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

        self.date_from_input = QDateEdit()
        self.date_from_input.setCalendarPopup(True)
        self.date_from_input.setDisplayFormat("yyyy-MM-dd")
        self.date_from_input.setDate(self.date_from_input.date())

        self.date_to_input = QDateEdit()
        self.date_to_input.setCalendarPopup(True)
        self.date_to_input.setDisplayFormat("yyyy-MM-dd")
        self.date_to_input.setDate(self.date_to_input.date())

        self.reason_input = QLineEdit()
        self.reason_input.returnPressed.connect(self._save)

        form = QFormLayout()
        form.addRow("Employee", self.employee_combo)
        form.addRow("From", self.date_from_input)
        form.addRow("To", self.date_to_input)
        form.addRow("Reason", self.reason_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Request Leave")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        if self.employee_combo.count() == 0:
            self._show_error("No employees available.")
            return
        try:
            data = LeaveRequestCreate(
                employee_id=self.employee_combo.currentData(),
                date_from=self.date_from_input.date().toPython(),
                date_to=self.date_to_input.date().toPython(),
                reason=self.reason_input.text(),
            )
            self._leave_service.request_leave(self._actor_user_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
