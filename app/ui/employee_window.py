"""Employee/HR UI: list, add, edit, status/exit workflow, and documents.

Pure presentation layer — all validation and business rules live in
EmployeeService/EmployeeCreate/EmployeeUpdate. Widgets only collect input,
call the service, and render the result or the error it raises.
"""

from datetime import date

from pydantic import ValidationError
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import EmployeeStatus, Permission
from app.core.exceptions import AppError
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error, qdate_to_date
from app.ui.widgets import GridBackgroundWidget, confirm_dialog

TABLE_HEADERS = ["Code", "Name", "Designation", "Department", "Status", "Joining Date"]


class EmployeeListWindow(QWidget):
    """Searchable employee list with add/view actions."""

    def __init__(self, employee_service, auth_service, actor_user_id: str):
        super().__init__()
        self._employee_service = employee_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id
        self._can_manage = auth_service.check_permission(actor_user_id, Permission.EMPLOYEE_MANAGE.value)
        self._all_employees = []

        self.setWindowTitle("Employees")
        self.setMinimumSize(820, 560)

        title = QLabel("Employees")
        title.setObjectName("title")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or employee code...")
        self.search_input.textChanged.connect(self._apply_filter)

        self.add_button = QPushButton("+ Add Employee")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(self._can_manage)

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(self.search_input, stretch=1)
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(TABLE_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(TABLE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._open_selected_employee)

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
        self._all_employees = self._employee_service.list_employees(self._actor_user_id)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search_input.text().strip().lower()
        rows = [
            e
            for e in self._all_employees
            if query in e.employee_code.lower() or query in f"{e.first_name} {e.last_name}".lower()
        ]
        self.table.setRowCount(len(rows))
        for row_index, employee in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(employee.employee_code))
            self.table.setItem(row_index, 1, QTableWidgetItem(f"{employee.first_name} {employee.last_name}"))
            self.table.setItem(row_index, 2, QTableWidgetItem(employee.designation or ""))
            self.table.setItem(row_index, 3, QTableWidgetItem(employee.department or ""))
            self.table.setItem(row_index, 4, QTableWidgetItem(employee.status.replace("_", " ").title()))
            self.table.setItem(row_index, 5, QTableWidgetItem(employee.joining_date.isoformat()))
            self.table.item(row_index, 0).setData(Qt.UserRole, employee.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = EmployeeFormDialog(self._employee_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_selected_employee(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        employee_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        dialog = EmployeeDetailDialog(self._employee_service, self._actor_user_id, employee_id, self._can_manage, self)
        dialog.exec()
        self.refresh()


class EmployeeFormDialog(QDialog):
    """Add-employee form. Builds an EmployeeCreate and delegates to EmployeeService."""

    def __init__(self, employee_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._employee_service = employee_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Add Employee")
        self.setMinimumWidth(420)

        self.first_name_input = QLineEdit()
        self.last_name_input = QLineEdit()
        self.contact_input = QLineEdit()
        self.contact_input.setPlaceholderText("e.g. +91 9876543210")
        self.email_input = QLineEdit()
        self.designation_input = QLineEdit()
        self.department_input = QLineEdit()
        self.outlet_input = QLineEdit()
        self.outlet_input.setText("Main Outlet")
        self.joining_date_input = QDateEdit(QDate.currentDate())
        self.joining_date_input.setCalendarPopup(True)
        self.emergency_name_input = QLineEdit()
        self.emergency_phone_input = QLineEdit()
        self.emergency_phone_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(
            self.first_name_input,
            self.last_name_input,
            self.contact_input,
            self.email_input,
            self.designation_input,
            self.department_input,
            self.outlet_input,
            self.joining_date_input,
            self.emergency_name_input,
            self.emergency_phone_input,
        )

        form = QFormLayout()
        form.addRow("First name", self.first_name_input)
        form.addRow("Last name", self.last_name_input)
        form.addRow("Contact number", self.contact_input)
        form.addRow("Email", self.email_input)
        form.addRow("Designation", self.designation_input)
        form.addRow("Department", self.department_input)
        form.addRow("Assigned outlet", self.outlet_input)
        form.addRow("Joining date", self.joining_date_input)
        form.addRow("Emergency contact name", self.emergency_name_input)
        form.addRow("Emergency contact phone", self.emergency_phone_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Save")
        save_button.setCursor(Qt.PointingHandCursor)
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
            data = EmployeeCreate(
                first_name=self.first_name_input.text(),
                last_name=self.last_name_input.text(),
                contact_number=self.contact_input.text().strip(),
                email=self.email_input.text().strip() or None,
                designation=self.designation_input.text().strip() or None,
                department=self.department_input.text().strip() or None,
                assigned_outlet=self.outlet_input.text().strip() or None,
                joining_date=qdate_to_date(self.joining_date_input.date()),
                emergency_contact_name=self.emergency_name_input.text().strip() or None,
                emergency_contact_phone=self.emergency_phone_input.text().strip() or None,
            )
            self._employee_service.create_employee(self._actor_user_id, data)
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


class EmployeeDetailDialog(QDialog):
    """View/edit an employee: profile fields, status/exit workflow, documents."""

    def __init__(self, employee_service, actor_user_id: str, employee_id: str, can_manage: bool, parent=None):
        super().__init__(parent)
        self._employee_service = employee_service
        self._actor_user_id = actor_user_id
        self._employee_id = employee_id
        self._can_manage = can_manage
        self._employee = employee_service.get_employee(actor_user_id, employee_id)

        self.setWindowTitle(f"{self._employee.first_name} {self._employee.last_name} ({self._employee.employee_code})")
        self.setMinimumWidth(480)

        layout = QVBoxLayout()
        layout.addLayout(self._build_profile_section())
        layout.addWidget(self._build_status_section())
        layout.addWidget(self._build_documents_section())

        close_button = QPushButton("Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.accept)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self.setLayout(layout)

    def _build_profile_section(self) -> QFormLayout:
        e = self._employee
        self.designation_input = QLineEdit(e.designation or "")
        self.department_input = QLineEdit(e.department or "")
        self.contact_input = QLineEdit(e.contact_number or "")
        self.department_input.returnPressed.connect(self._save_profile)

        chain_enter_to_next_field(self.contact_input, self.designation_input, self.department_input)

        form = QFormLayout()
        form.addRow("Contact number", self.contact_input)
        form.addRow("Designation", self.designation_input)
        form.addRow("Department", self.department_input)

        self.save_profile_button = QPushButton("Save Profile")
        self.save_profile_button.setEnabled(self._can_manage)
        self.save_profile_button.clicked.connect(self._save_profile)
        form.addRow("", self.save_profile_button)
        return form

    def _save_profile(self) -> None:
        try:
            self._employee = self._employee_service.update_employee(
                self._actor_user_id,
                self._employee_id,
                EmployeeUpdate(
                    contact_number=self.contact_input.text().strip() or None,
                    designation=self.designation_input.text().strip() or None,
                    department=self.department_input.text().strip() or None,
                ),
            )
        except (ValidationError, AppError) as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not save", describe_unexpected_error(exc))

    def _build_status_section(self) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout()

        section_title = QLabel("Status")
        section_title.setObjectName("sectionTitle")
        layout.addWidget(section_title)

        row = QHBoxLayout()
        self.status_combo = QComboBox()
        self.status_combo.addItems([s.value for s in EmployeeStatus])
        self.status_combo.setCurrentText(self._employee.status)
        self.status_combo.setEnabled(self._can_manage)

        self.apply_status_button = QPushButton("Apply")
        self.apply_status_button.setEnabled(self._can_manage)
        self.apply_status_button.clicked.connect(self._apply_status_change)

        self.exit_button = QPushButton("Record Exit")
        self.exit_button.setObjectName("dangerButton")
        self.exit_button.setEnabled(self._can_manage)
        self.exit_button.clicked.connect(self._record_exit)

        row.addWidget(self.status_combo)
        row.addWidget(self.apply_status_button)
        row.addWidget(self.exit_button)
        layout.addLayout(row)

        section.setLayout(layout)
        return section

    def _apply_status_change(self) -> None:
        reason, ok = QInputDialog.getText(self, "Change status", "Reason for status change:")
        if not ok or not reason.strip():
            return
        try:
            self._employee = self._employee_service.change_status(
                self._actor_user_id, self._employee_id, EmployeeStatus(self.status_combo.currentText()), reason.strip()
            )
        except AppError as exc:
            QMessageBox.warning(self, "Could not change status", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change status", describe_unexpected_error(exc))

    def _record_exit(self) -> None:
        confirm = confirm_dialog(
            self,
            "Confirm exit",
            "This will mark the employee as terminated. Continue?",
            [("Cancel", "secondaryButton"), ("Mark as Exited", "dangerButton")],
        )
        if confirm != "Mark as Exited":
            return

        reason, ok = QInputDialog.getText(self, "Record exit", "Reason for exit:")
        if not ok or not reason.strip():
            return
        try:
            self._employee = self._employee_service.record_exit(
                self._actor_user_id, self._employee_id, date.today(), reason.strip()
            )
            self.status_combo.setCurrentText(self._employee.status)
        except AppError as exc:
            QMessageBox.warning(self, "Could not record exit", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not record exit", describe_unexpected_error(exc))

    def _build_documents_section(self) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout()

        section_title = QLabel("Documents")
        section_title.setObjectName("sectionTitle")
        layout.addWidget(section_title)

        self.documents_list = QListWidget()
        layout.addWidget(self.documents_list)

        row = QHBoxLayout()
        self.add_document_button = QPushButton("Add Document")
        self.add_document_button.setEnabled(self._can_manage)
        self.add_document_button.clicked.connect(self._add_document)

        self.remove_document_button = QPushButton("Remove Selected")
        self.remove_document_button.setObjectName("dangerButton")
        self.remove_document_button.setEnabled(self._can_manage)
        self.remove_document_button.clicked.connect(self._remove_selected_document)

        row.addWidget(self.add_document_button)
        row.addWidget(self.remove_document_button)
        layout.addLayout(row)

        section.setLayout(layout)
        self._refresh_documents()
        return section

    def _refresh_documents(self) -> None:
        self.documents_list.clear()
        for document in self._employee_service.list_documents(self._actor_user_id, self._employee_id):
            item = QListWidgetItem(f"{document.document_type} — {document.file_reference}")
            item.setData(Qt.UserRole, document.id)
            self.documents_list.addItem(item)

    def _add_document(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select document")
        if not file_path:
            return
        document_type, ok = QInputDialog.getText(self, "Document type", "e.g. ID Proof, Address Proof, Photo:")
        if not ok or not document_type.strip():
            return
        try:
            self._employee_service.add_document(self._actor_user_id, self._employee_id, document_type.strip(), file_path)
            self._refresh_documents()
        except AppError as exc:
            QMessageBox.warning(self, "Could not add document", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not add document", describe_unexpected_error(exc))

    def _remove_selected_document(self) -> None:
        item = self.documents_list.currentItem()
        if not item:
            return
        confirm = confirm_dialog(
            self, "Remove document", "Remove this document?",
            [("Cancel", "secondaryButton"), ("Remove", "dangerButton")],
        )
        if confirm != "Remove":
            return
        reason, ok = QInputDialog.getText(self, "Remove document", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._employee_service.remove_document(self._actor_user_id, item.data(Qt.UserRole), reason.strip())
            self._refresh_documents()
        except AppError as exc:
            QMessageBox.warning(self, "Could not remove document", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not remove document", describe_unexpected_error(exc))
