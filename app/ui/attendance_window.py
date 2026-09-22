"""Attendance UI: daily roster view, marking, and the correction workflow.

Pure presentation — validation and business rules live in AttendanceService
and its Pydantic schemas.
"""

from pydantic import ValidationError
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import AttendanceStatus, EmployeeStatus, Permission
from app.core.exceptions import AppError
from app.schemas.attendance import AttendanceCorrection, AttendanceMark
from app.ui.qt_utils import describe_unexpected_error, make_edit_icon_button, qdate_to_date
from app.ui.widgets import GridBackgroundWidget

TABLE_HEADERS = ["Employee", "Status", "Check In", "Check Out", "Overtime (min)", "Corrected", ""]


class AttendanceWindow(QWidget):
    """Daily attendance roster: pick a date, view who's marked, mark/correct entries."""

    def __init__(self, attendance_service, employee_service, auth_service, actor_user_id: str):
        super().__init__()
        self._attendance_service = attendance_service
        self._employee_service = employee_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id
        self._can_manage = auth_service.check_permission(actor_user_id, Permission.ATTENDANCE_MANAGE.value)
        self._records = []

        self.setWindowTitle("Attendance")
        self.setMinimumSize(820, 560)

        title = QLabel("Attendance")
        title.setObjectName("title")

        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.dateChanged.connect(self.refresh)

        self.mark_button = QPushButton("+ Mark Attendance")
        self.mark_button.setCursor(Qt.PointingHandCursor)
        self.mark_button.clicked.connect(self._open_mark_dialog)

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(QLabel("Date:"))
        top_row.addWidget(self.date_input)
        top_row.addWidget(self.mark_button)

        self.table = QTableWidget(0, len(TABLE_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(TABLE_HEADERS)
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

        # Deferred until mark_button is actually parented (2026-09-16,
        # user-reported flicker): a QPushButton constructed with no
        # parent is its own independent top-level window as far as Qt
        # is concerned until something reparents it - here that happens
        # the moment container.setLayout(layout) runs above. Calling
        # setVisible(True) any earlier genuinely shows it as a real,
        # separate OS window for however long it takes Qt to get to
        # that point, long enough to be visibly seen.
        self.mark_button.setVisible(self._can_manage)

        self.refresh()

    def refresh(self) -> None:
        attendance_date = qdate_to_date(self.date_input.date())
        self._records = self._attendance_service.list_for_date(self._actor_user_id, attendance_date)
        records_by_employee = {record.employee_id: record for record in self._records}

        # The roster is every active employee, not just those already
        # marked - this is what lets Present/Absent be marked inline
        # per row below, instead of only through "+ Mark Attendance".
        employees = [
            e
            for e in self._employee_service.list_employees(self._actor_user_id)
            if e.status == EmployeeStatus.ACTIVE.value
        ]
        employees.sort(key=lambda e: (e.first_name, e.last_name))

        self.table.setRowCount(len(employees))
        for row_index, employee in enumerate(employees):
            record = records_by_employee.get(employee.id)

            name_item = QTableWidgetItem(f"{employee.first_name} {employee.last_name}")
            name_item.setData(Qt.UserRole, employee.id)
            self.table.setItem(row_index, 0, name_item)

            for col in (1, 2, 3, 4, 5, 6):
                self.table.setCellWidget(row_index, col, None)
                self.table.setItem(row_index, col, None)

            if record:
                self.table.setItem(row_index, 1, QTableWidgetItem(record.status.replace("_", " ").title()))
                self.table.setItem(row_index, 2, QTableWidgetItem(record.check_in_time.strftime("%H:%M") if record.check_in_time else ""))
                self.table.setItem(row_index, 3, QTableWidgetItem(record.check_out_time.strftime("%H:%M") if record.check_out_time else ""))
                self.table.setItem(row_index, 4, QTableWidgetItem(str(record.overtime_minutes)))
                self.table.setItem(row_index, 5, QTableWidgetItem("Yes" if record.corrected_at else ""))
                if self._can_manage:
                    self.table.setCellWidget(
                        row_index, 6, make_edit_icon_button(lambda _=False, rid=record.id: self._open_correction_dialog(rid))
                    )
            elif self._can_manage:
                self.table.setCellWidget(row_index, 1, self._make_quick_mark_widget(employee.id))
            else:
                self.table.setItem(row_index, 1, QTableWidgetItem("Not marked"))

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _make_quick_mark_widget(self, employee_id: str) -> QWidget:
        """Present/Absent, one click each - the inline path for the
        everyday case. Anything else (Late, Half Day, Leave, Holiday) or
        a correction to an already-marked row still goes through the
        dialogs below.
        """
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        present_button = QPushButton("Present")
        present_button.setCursor(Qt.PointingHandCursor)
        present_button.clicked.connect(lambda _=False, eid=employee_id: self._quick_mark(eid, AttendanceStatus.PRESENT))

        absent_button = QPushButton("Absent")
        absent_button.setObjectName("secondaryButton")
        absent_button.setCursor(Qt.PointingHandCursor)
        absent_button.clicked.connect(lambda _=False, eid=employee_id: self._quick_mark(eid, AttendanceStatus.ABSENT))

        row.addWidget(present_button)
        row.addWidget(absent_button)
        row.addStretch()
        return widget

    def _quick_mark(self, employee_id: str, status: AttendanceStatus) -> None:
        try:
            data = AttendanceMark(
                employee_id=employee_id,
                attendance_date=qdate_to_date(self.date_input.date()),
                status=status,
            )
            self._attendance_service.mark_attendance(self._actor_user_id, data)
        except ValidationError as exc:
            QMessageBox.warning(self, "Could not mark attendance", "; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            QMessageBox.warning(self, "Could not mark attendance", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the window
            QMessageBox.warning(self, "Could not mark attendance", describe_unexpected_error(exc))
            return

        self.refresh()

    def _open_mark_dialog(self) -> None:
        dialog = AttendanceMarkDialog(
            self._attendance_service, self._employee_service, self._actor_user_id, self.date_input.date(), self
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_correction_dialog(self, attendance_id: str) -> None:
        dialog = AttendanceCorrectionDialog(self._attendance_service, self._actor_user_id, attendance_id, self._can_manage, self)
        dialog.exec()
        self.refresh()


class AttendanceMarkDialog(QDialog):
    """Mark a new attendance record for one employee on one date."""

    def __init__(self, attendance_service, employee_service, actor_user_id: str, default_date: QDate, parent=None):
        super().__init__(parent)
        self._attendance_service = attendance_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Mark Attendance")
        self.setMinimumWidth(380)

        self.employee_combo = QComboBox()
        self._employees = employee_service.list_employees(actor_user_id)
        for employee in self._employees:
            self.employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

        self.date_input = QDateEdit(default_date)
        self.date_input.setCalendarPopup(True)

        self.status_combo = QComboBox()
        self.status_combo.addItems([s.value for s in AttendanceStatus])

        self.shift_input = QLineEdit()
        self.shift_input.setPlaceholderText("e.g. Morning")
        self.shift_input.returnPressed.connect(self._save)

        self.overtime_input = QSpinBox()
        self.overtime_input.setRange(0, 1440)
        self.overtime_input.setSuffix(" min")

        form = QFormLayout()
        form.addRow("Employee", self.employee_combo)
        form.addRow("Date", self.date_input)
        form.addRow("Status", self.status_combo)
        form.addRow("Shift", self.shift_input)
        form.addRow("Overtime", self.overtime_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Save")
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
            self._show_error("No employees available to mark attendance for.")
            return
        try:
            data = AttendanceMark(
                employee_id=self.employee_combo.currentData(),
                attendance_date=qdate_to_date(self.date_input.date()),
                status=AttendanceStatus(self.status_combo.currentText()),
                shift_label=self.shift_input.text().strip() or None,
                overtime_minutes=self.overtime_input.value(),
            )
            self._attendance_service.mark_attendance(self._actor_user_id, data)
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


class AttendanceCorrectionDialog(QDialog):
    """Correct an existing attendance record. Requires a reason; audit-logged by the service."""

    def __init__(self, attendance_service, actor_user_id: str, attendance_id: str, can_manage: bool, parent=None):
        super().__init__(parent)
        self._attendance_service = attendance_service
        self._actor_user_id = actor_user_id
        self._attendance_id = attendance_id
        self._record = attendance_service.get_attendance(actor_user_id, attendance_id)

        self.setWindowTitle("Attendance Detail")
        self.setMinimumWidth(380)

        self.status_combo = QComboBox()
        self.status_combo.addItems([s.value for s in AttendanceStatus])
        self.status_combo.setCurrentText(self._record.status)
        self.status_combo.setEnabled(can_manage)

        self.overtime_input = QSpinBox()
        self.overtime_input.setRange(0, 1440)
        self.overtime_input.setSuffix(" min")
        self.overtime_input.setValue(self._record.overtime_minutes)
        self.overtime_input.setEnabled(can_manage)

        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("Reason for correction (required to save changes)")
        self.reason_input.setFixedHeight(60)
        self.reason_input.setEnabled(can_manage)

        form = QFormLayout()
        form.addRow("Status", self.status_combo)
        form.addRow("Overtime", self.overtime_input)
        form.addRow("Correction reason", self.reason_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        self.save_button = QPushButton("Save Correction")
        self.save_button.setEnabled(can_manage)
        self.save_button.clicked.connect(self._save)

        close_button = QPushButton("Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(close_button)
        button_row.addWidget(self.save_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        try:
            data = AttendanceCorrection(
                status=AttendanceStatus(self.status_combo.currentText()),
                overtime_minutes=self.overtime_input.value(),
            )
            self._attendance_service.correct_attendance(
                self._actor_user_id, self._attendance_id, data, self.reason_input.toPlainText()
            )
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except (AppError, ValueError) as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the dialog
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
