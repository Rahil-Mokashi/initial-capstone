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
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import AttendanceStatus, Permission
from app.core.exceptions import AppError
from app.schemas.attendance import AttendanceCorrection, AttendanceMark
from app.ui.qt_utils import qdate_to_date

TABLE_HEADERS = ["Employee", "Status", "Check In", "Check Out", "Overtime (min)", "Corrected"]


class AttendanceWindow(QMainWindow):
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
        self.mark_button.setVisible(self._can_manage)

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(QLabel("Date:"))
        top_row.addWidget(self.date_input)
        top_row.addWidget(self.mark_button)

        self.table = QTableWidget(0, len(TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(TABLE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._open_correction_dialog)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(top_row)
        layout.addWidget(self.table)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh()

    def refresh(self) -> None:
        attendance_date = qdate_to_date(self.date_input.date())
        self._records = self._attendance_service.list_for_date(self._actor_user_id, attendance_date)

        employees_by_id = {e.id: e for e in self._employee_service.list_employees(self._actor_user_id)}

        self.table.setRowCount(len(self._records))
        for row_index, record in enumerate(self._records):
            employee = employees_by_id.get(record.employee_id)
            name = f"{employee.first_name} {employee.last_name}" if employee else record.employee_id

            self.table.setItem(row_index, 0, QTableWidgetItem(name))
            self.table.setItem(row_index, 1, QTableWidgetItem(record.status.replace("_", " ").title()))
            self.table.setItem(row_index, 2, QTableWidgetItem(record.check_in_time.strftime("%H:%M") if record.check_in_time else ""))
            self.table.setItem(row_index, 3, QTableWidgetItem(record.check_out_time.strftime("%H:%M") if record.check_out_time else ""))
            self.table.setItem(row_index, 4, QTableWidgetItem(str(record.overtime_minutes)))
            self.table.setItem(row_index, 5, QTableWidgetItem("Yes" if record.corrected_at else ""))
            self.table.item(row_index, 0).setData(Qt.UserRole, record.id)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_mark_dialog(self) -> None:
        dialog = AttendanceMarkDialog(
            self._attendance_service, self._employee_service, self._actor_user_id, self.date_input.date(), self
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_correction_dialog(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        attendance_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
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

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
