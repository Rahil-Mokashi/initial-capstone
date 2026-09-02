"""Shift UI: open/close shifts, assign attendants to nozzles, reopen workflow.

Pure presentation — validation and business rules live in ShiftService and
its Pydantic schemas.
"""

from pydantic import ValidationError
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
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
    QWidget,
)

from app.core.constants import Permission
from app.core.exceptions import AppError
from app.schemas.shift import NozzleAssignmentComplete, NozzleAssignmentCreate, ShiftOpen
from app.ui.qt_utils import describe_unexpected_error, make_edit_icon_button, qdate_to_date
from app.ui.widgets import GridBackgroundWidget, confirm_dialog

SHIFT_TABLE_HEADERS = ["Date", "Shift", "Status", "Opened By", ""]
ASSIGNMENT_TABLE_HEADERS = ["Employee", "Nozzle", "Opening", "Closing", "Status", ""]


class ShiftListWindow(QWidget):
    def __init__(self, shift_service, employee_service, auth_service, actor_user_id: str):
        super().__init__()
        self._shift_service = shift_service
        self._employee_service = employee_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id
        self._can_manage = auth_service.check_permission(actor_user_id, Permission.SHIFT_MANAGE.value)
        self._shifts = []

        self.setWindowTitle("Shifts")
        self.setMinimumSize(760, 540)

        title = QLabel("Shifts")
        title.setObjectName("title")

        self.open_button = QPushButton("+ Open Shift")
        self.open_button.setCursor(Qt.PointingHandCursor)
        self.open_button.clicked.connect(self._open_shift_dialog)
        self.open_button.setVisible(self._can_manage)

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(self.open_button)

        self.table = QTableWidget(0, len(SHIFT_TABLE_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(SHIFT_TABLE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(top_row)
        layout.addWidget(self.table)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)

        self.refresh()

    def refresh(self) -> None:
        self._shifts = self._shift_service.list_shifts(self._actor_user_id)
        self.table.setRowCount(len(self._shifts))
        for row_index, shift in enumerate(self._shifts):
            self.table.setItem(row_index, 0, QTableWidgetItem(shift.shift_date.isoformat()))
            self.table.setItem(row_index, 1, QTableWidgetItem(shift.shift_label))
            self.table.setItem(row_index, 2, QTableWidgetItem(shift.status.title()))
            self.table.setItem(row_index, 3, QTableWidgetItem(shift.opened_by.username if shift.opened_by else ""))
            self.table.item(row_index, 0).setData(Qt.UserRole, shift.id)
            self.table.setCellWidget(
                row_index, 4, make_edit_icon_button(lambda _=False, sid=shift.id: self._open_shift(sid))
            )
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_shift_dialog(self) -> None:
        dialog = ShiftOpenDialog(self._shift_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_shift(self, shift_id: str) -> None:
        dialog = ShiftDetailDialog(self._shift_service, self._employee_service, self._auth_service, self._actor_user_id, shift_id, self)
        dialog.exec()
        self.refresh()


class ShiftOpenDialog(QDialog):
    def __init__(self, shift_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._shift_service = shift_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Open Shift")
        self.setMinimumWidth(360)

        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)

        self.label_input = QComboBox()
        self.label_input.setEditable(True)
        self.label_input.addItems(["Morning", "Afternoon", "Evening", "Night"])

        self.notes_input = QLineEdit()
        self.notes_input.returnPressed.connect(self._save)

        form = QFormLayout()
        form.addRow("Date", self.date_input)
        form.addRow("Shift", self.label_input)
        form.addRow("Notes", self.notes_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Open")
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
        try:
            data = ShiftOpen(
                shift_date=qdate_to_date(self.date_input.date()),
                shift_label=self.label_input.currentText(),
                notes=self.notes_input.text().strip() or None,
            )
            self._shift_service.open_shift(self._actor_user_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the dialog
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


class ShiftDetailDialog(QDialog):
    def __init__(self, shift_service, employee_service, auth_service, actor_user_id: str, shift_id: str, parent=None):
        super().__init__(parent)
        self._shift_service = shift_service
        self._employee_service = employee_service
        self._actor_user_id = actor_user_id
        self._shift_id = shift_id
        self._can_manage = auth_service.check_permission(actor_user_id, Permission.SHIFT_MANAGE.value)
        self._can_reopen = auth_service.check_permission(actor_user_id, Permission.SHIFT_REOPEN.value)
        self._shift = shift_service.get_shift(actor_user_id, shift_id)

        self.setWindowTitle(f"{self._shift.shift_label} shift - {self._shift.shift_date}")
        self.setMinimumSize(560, 480)

        self.status_label = QLabel()
        self.status_label.setObjectName("sectionTitle")

        self.assign_button = QPushButton("Assign Nozzle")
        self.assign_button.clicked.connect(self._open_assign_dialog)

        self.close_button = QPushButton("Close Shift")
        self.close_button.setObjectName("dangerButton")
        self.close_button.clicked.connect(self._close_shift)

        self.reopen_button = QPushButton("Reopen Shift")
        self.reopen_button.setObjectName("dangerButton")
        self.reopen_button.clicked.connect(self._reopen_shift)

        action_row = QHBoxLayout()
        action_row.addWidget(self.status_label)
        action_row.addStretch()
        action_row.addWidget(self.assign_button)
        action_row.addWidget(self.close_button)
        action_row.addWidget(self.reopen_button)

        self.table = QTableWidget(0, len(ASSIGNMENT_TABLE_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(ASSIGNMENT_TABLE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        close_dialog_button = QPushButton("Close")
        close_dialog_button.setObjectName("secondaryButton")
        close_dialog_button.clicked.connect(self.accept)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(close_dialog_button)

        layout = QVBoxLayout()
        layout.addLayout(action_row)
        layout.addWidget(self.table)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

        self._refresh()

    def _refresh(self) -> None:
        self._shift = self._shift_service.get_shift(self._actor_user_id, self._shift_id)
        self.status_label.setText(f"Status: {self._shift.status.title()}")

        is_open = self._shift.status == "open"
        self.assign_button.setEnabled(self._can_manage and is_open)
        self.close_button.setEnabled(self._can_manage and is_open)
        self.reopen_button.setEnabled(self._can_reopen and not is_open)

        assignments = self._shift_service.list_nozzle_assignments(self._actor_user_id, self._shift_id)
        self.table.setRowCount(len(assignments))
        for row_index, assignment in enumerate(assignments):
            employee = assignment.employee
            self.table.setItem(row_index, 0, QTableWidgetItem(f"{employee.first_name} {employee.last_name}" if employee else ""))
            self.table.setItem(row_index, 1, QTableWidgetItem(assignment.nozzle.code if assignment.nozzle else ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(str(assignment.opening_meter)))
            self.table.setItem(row_index, 3, QTableWidgetItem(str(assignment.closing_meter) if assignment.closing_meter is not None else ""))
            self.table.setItem(row_index, 4, QTableWidgetItem(assignment.status.title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, assignment.id)
            if assignment.status == "active" and self._can_manage:
                self.table.setCellWidget(
                    row_index, 5,
                    make_edit_icon_button(lambda _=False, aid=assignment.id: self._open_assignment_action(aid)),
                )
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_assign_dialog(self) -> None:
        dialog = NozzleAssignDialog(self._shift_service, self._employee_service, self._actor_user_id, self._shift_id, self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh()

    def _open_assignment_action(self, assignment_id: str) -> None:
        choice = confirm_dialog(
            self,
            "Nozzle assignment",
            "Complete this assignment, or cancel it instead?",
            [("Dismiss", "secondaryButton"), ("Cancel Assignment", "dangerButton"), ("Complete Assignment", "")],
        )
        if choice in (None, "Dismiss"):
            return
        if choice == "Complete Assignment":
            closing_meter, ok = QInputDialog.getDouble(self, "Closing meter", "Closing meter reading:", 0, 0, 10_000_000, 2)
            if not ok:
                return
            try:
                self._shift_service.complete_nozzle_assignment(
                    self._actor_user_id, assignment_id, NozzleAssignmentComplete(closing_meter=closing_meter)
                )
            except (ValidationError, AppError, ValueError) as exc:
                QMessageBox.warning(self, "Could not complete assignment", str(exc))
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Could not complete assignment", describe_unexpected_error(exc))
        else:
            reason, ok = QInputDialog.getText(self, "Cancel assignment", "Reason:")
            if not ok or not reason.strip():
                return
            try:
                self._shift_service.cancel_nozzle_assignment(self._actor_user_id, assignment_id, reason.strip())
            except (AppError, ValueError) as exc:
                QMessageBox.warning(self, "Could not cancel assignment", str(exc))
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Could not cancel assignment", describe_unexpected_error(exc))
        self._refresh()

    def _close_shift(self) -> None:
        confirm = confirm_dialog(
            self, "Close shift", "Close this shift? Active assignments must be completed or cancelled first.",
            [("Cancel", "secondaryButton"), ("Close Shift", "dangerButton")],
        )
        if confirm != "Close Shift":
            return
        try:
            self._shift_service.close_shift(self._actor_user_id, self._shift_id)
        except AppError as exc:
            QMessageBox.warning(self, "Could not close shift", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not close shift", describe_unexpected_error(exc))
        self._refresh()

    def _reopen_shift(self) -> None:
        reason, ok = QInputDialog.getText(self, "Reopen shift", "Reason for reopening:")
        if not ok or not reason.strip():
            return
        try:
            self._shift_service.reopen_shift(self._actor_user_id, self._shift_id, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not reopen shift", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not reopen shift", describe_unexpected_error(exc))
        self._refresh()


class NozzleAssignDialog(QDialog):
    def __init__(self, shift_service, employee_service, actor_user_id: str, shift_id: str, parent=None):
        super().__init__(parent)
        self._shift_service = shift_service
        self._actor_user_id = actor_user_id
        self._shift_id = shift_id

        self.setWindowTitle("Assign Nozzle")
        self.setMinimumWidth(360)

        self.employee_combo = QComboBox()
        for employee in employee_service.list_employees(actor_user_id):
            self.employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

        self.nozzle_combo = QComboBox()
        for nozzle in shift_service.list_active_nozzles(actor_user_id):
            self.nozzle_combo.addItem(nozzle.code, nozzle.id)

        self.opening_meter_input = QDoubleSpinBox()
        self.opening_meter_input.setRange(0, 10_000_000)
        self.opening_meter_input.setDecimals(2)

        form = QFormLayout()
        form.addRow("Employee", self.employee_combo)
        form.addRow("Nozzle", self.nozzle_combo)
        form.addRow("Opening meter", self.opening_meter_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Assign")
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
        if self.employee_combo.count() == 0 or self.nozzle_combo.count() == 0:
            self._show_error("No employees or active nozzles available.")
            return
        try:
            data = NozzleAssignmentCreate(
                employee_id=self.employee_combo.currentData(),
                nozzle_id=self.nozzle_combo.currentData(),
                opening_meter=self.opening_meter_input.value(),
            )
            self._shift_service.assign_nozzle(self._actor_user_id, self._shift_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the dialog
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
