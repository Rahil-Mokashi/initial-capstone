"""Expense Management UI (Phase 14). Two tabs: Expenses, Categories."""

from decimal import Decimal

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import PaymentMethod, Permission
from app.core.exceptions import AppError
from app.schemas.expense import ExpenseCategoryCreate, ExpenseCreate
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget

EXPENSE_HEADERS = ["Date", "Category", "Amount", "Method", "Employee", "Status"]
CATEGORY_HEADERS = ["Name", "Status"]


class ExpenseWindow(QWidget):
    def __init__(self, expense_service, employee_service, shift_service, auth_service, actor_user_id: str):
        super().__init__()
        self.setWindowTitle("Expenses")
        self.setMinimumSize(860, 600)

        title = QLabel("Expenses")
        title.setObjectName("title")

        can_manage = auth_service.check_permission(actor_user_id, Permission.EXPENSE_MANAGE.value)
        can_approve = auth_service.check_permission(actor_user_id, Permission.EXPENSE_APPROVE.value)
        self.expenses_tab = ExpensesTab(
            expense_service, employee_service, shift_service, auth_service, actor_user_id, can_manage, can_approve
        )
        self.categories_tab = ExpenseCategoriesTab(expense_service, actor_user_id, can_manage)

        tabs = QTabWidget()
        tabs.addTab(self.expenses_tab, "Expenses")
        tabs.addTab(self.categories_tab, "Categories")
        tabs.currentChanged.connect(lambda _: (self.expenses_tab.refresh(), self.categories_tab.refresh()))

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(tabs)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)


class ExpensesTab(QWidget):
    def __init__(self, expense_service, employee_service, shift_service, auth_service, actor_user_id: str, can_manage: bool, can_approve: bool):
        super().__init__()
        self._expense_service = expense_service
        self._employee_service = employee_service
        self._shift_service = shift_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id

        self.add_button = QPushButton("+ Record Expense")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        self.approve_button = QPushButton("Approve Selected")
        self.approve_button.setObjectName("secondaryButton")
        self.approve_button.clicked.connect(self._approve_selected)
        self.approve_button.setVisible(can_approve)

        self.reject_button = QPushButton("Reject Selected")
        self.reject_button.setObjectName("dangerButton")
        self.reject_button.clicked.connect(self._reject_selected)
        self.reject_button.setVisible(can_approve)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.reject_button)
        top_row.addWidget(self.approve_button)
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(EXPENSE_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(EXPENSE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        expenses = self._expense_service.list_expenses(self._actor_user_id)
        self.table.setRowCount(len(expenses))
        for row_index, expense in enumerate(expenses):
            self.table.setItem(row_index, 0, QTableWidgetItem(expense.expense_date.strftime("%Y-%m-%d")))
            self.table.setItem(row_index, 1, QTableWidgetItem(expense.category.name if expense.category else ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(f"{expense.amount:g}"))
            self.table.setItem(row_index, 3, QTableWidgetItem(expense.payment_method.title()))
            employee_name = f"{expense.employee.first_name} {expense.employee.last_name}" if expense.employee else ""
            self.table.setItem(row_index, 4, QTableWidgetItem(employee_name))
            self.table.setItem(row_index, 5, QTableWidgetItem(expense.status.title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, expense.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = ExpenseFormDialog(
            self._expense_service, self._employee_service, self._shift_service, self._actor_user_id, self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _selected_expense_id(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def _approve_selected(self) -> None:
        expense_id = self._selected_expense_id()
        if not expense_id:
            QMessageBox.information(self, "Approve expense", "Select an expense to approve first.")
            return
        remarks, ok = QInputDialog.getText(self, "Approve expense", "Remarks (optional):")
        if not ok:
            return
        try:
            self._expense_service.approve_expense(self._actor_user_id, expense_id, remarks.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not approve expense", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not approve expense", describe_unexpected_error(exc))
        self.refresh()

    def _reject_selected(self) -> None:
        expense_id = self._selected_expense_id()
        if not expense_id:
            QMessageBox.information(self, "Reject expense", "Select an expense to reject first.")
            return
        reason, ok = QInputDialog.getText(self, "Reject expense", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._expense_service.reject_expense(self._actor_user_id, expense_id, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not reject expense", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not reject expense", describe_unexpected_error(exc))
        self.refresh()


class ExpenseFormDialog(QDialog):
    def __init__(self, expense_service, employee_service, shift_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._expense_service = expense_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Record Expense")
        self.setMinimumWidth(400)

        self.category_combo = QComboBox()
        for category in expense_service.list_categories(actor_user_id):
            if category.status == "active":
                self.category_combo.addItem(category.name, category.id)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.01, 10_000_000)
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(500)

        self.method_combo = QComboBox()
        for method in PaymentMethod:
            if method != PaymentMethod.CREDIT:
                self.method_combo.addItem(method.value.title(), method)

        self.employee_combo = QComboBox()
        for employee in employee_service.list_employees(actor_user_id):
            self.employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

        self.shift_combo = QComboBox()
        self.shift_combo.addItem("(none)", None)
        for shift in shift_service.list_shifts(actor_user_id):
            if shift.status == "open":
                self.shift_combo.addItem(f"{shift.shift_date} {shift.shift_label}", shift.id)

        self.receipt_input = QLineEdit()
        self.description_input = QLineEdit()
        self.description_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(self.receipt_input, self.description_input)

        form = QFormLayout()
        form.addRow("Category", self.category_combo)
        form.addRow("Amount", self.amount_input)
        form.addRow("Payment method", self.method_combo)
        form.addRow("Employee", self.employee_combo)
        form.addRow("Shift", self.shift_combo)
        form.addRow("Receipt reference", self.receipt_input)
        form.addRow("Description", self.description_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Record Expense")
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
        if self.category_combo.count() == 0:
            self._show_error("No expense categories available - add one from the Categories tab first.")
            return
        if self.employee_combo.count() == 0:
            self._show_error("No employees available.")
            return
        try:
            data = ExpenseCreate(
                category_id=self.category_combo.currentData(),
                amount=Decimal(str(self.amount_input.value())),
                payment_method=self.method_combo.currentData(),
                employee_id=self.employee_combo.currentData(),
                shift_id=self.shift_combo.currentData(),
                receipt_reference=self.receipt_input.text().strip() or None,
                description=self.description_input.text().strip() or None,
            )
            self._expense_service.create_expense(self._actor_user_id, data)
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


class ExpenseCategoriesTab(QWidget):
    def __init__(self, expense_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._expense_service = expense_service
        self._actor_user_id = actor_user_id

        self.add_button = QPushButton("+ Add Category")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(CATEGORY_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(CATEGORY_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        categories = self._expense_service.list_categories(self._actor_user_id)
        self.table.setRowCount(len(categories))
        for row_index, category in enumerate(categories):
            self.table.setItem(row_index, 0, QTableWidgetItem(category.name))
            self.table.setItem(row_index, 1, QTableWidgetItem(category.status.title()))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = ExpenseCategoryFormDialog(self._expense_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()


class ExpenseCategoryFormDialog(QDialog):
    def __init__(self, expense_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._expense_service = expense_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Add Expense Category")
        self.setMinimumWidth(340)

        self.name_input = QLineEdit()
        self.name_input.returnPressed.connect(self._save)

        form = QFormLayout()
        form.addRow("Name", self.name_input)

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
        try:
            data = ExpenseCategoryCreate(name=self.name_input.text())
            self._expense_service.create_category(self._actor_user_id, data)
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
