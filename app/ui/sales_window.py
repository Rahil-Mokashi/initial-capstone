"""Sales UI (Phase 11). Two tabs: Sales, Customers.

Recording a sale has two paths depending on the actor's role: someone
with SHIFT_VIEW (Manager/Supervisor/Admin/Owner) gets a full shift/
nozzle/employee picker; an attendant (SALE_MANAGE only, no SHIFT_VIEW/
EMPLOYEE_VIEW) gets their own current nozzle assignment resolved
automatically via ShiftService.get_my_active_assignment - the same
self-service lookup "My Shift" already uses - rather than a picker they
don't have permission to populate.
"""

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
    QMainWindow,
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
from app.database.base import StatusEnum
from app.schemas.customer import CustomerCreate
from app.schemas.sale import SaleCreate
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error

SALE_HEADERS = ["Receipt #", "When", "Fuel", "Quantity", "Amount", "Method", "Sale Status", "Payment Status"]
CUSTOMER_HEADERS = ["Name", "Phone", "Status"]


class SalesWindow(QMainWindow):
    def __init__(self, sale_service, shift_service, employee_service, auth_service, actor_user_id: str):
        super().__init__()
        self.setWindowTitle("Sales")
        self.setMinimumSize(860, 600)

        title = QLabel("Sales")
        title.setObjectName("title")

        can_manage = auth_service.check_permission(actor_user_id, Permission.SALE_MANAGE.value)
        self.sales_tab = SalesTab(
            sale_service, shift_service, employee_service, auth_service, actor_user_id, can_manage
        )
        self.customers_tab = CustomersTab(sale_service, actor_user_id, can_manage)

        tabs = QTabWidget()
        tabs.addTab(self.sales_tab, "Sales")
        tabs.addTab(self.customers_tab, "Customers")
        tabs.currentChanged.connect(lambda _: (self.sales_tab.refresh(), self.customers_tab.refresh()))

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(tabs)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)


class SalesTab(QWidget):
    def __init__(self, sale_service, shift_service, employee_service, auth_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._sale_service = sale_service
        self._shift_service = shift_service
        self._employee_service = employee_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id

        self.add_button = QPushButton("+ Record Sale")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        self.cancel_button = QPushButton("Cancel Selected")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self._cancel_selected)
        self.cancel_button.setVisible(can_manage)

        self.mark_failed_button = QPushButton("Mark Payment Failed")
        self.mark_failed_button.setObjectName("secondaryButton")
        self.mark_failed_button.clicked.connect(self._mark_selected_payment_failed)
        self.mark_failed_button.setVisible(can_manage)

        self.refund_button = QPushButton("Refund Payment")
        self.refund_button.setObjectName("secondaryButton")
        self.refund_button.clicked.connect(self._refund_selected_payment)
        self.refund_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.refund_button)
        top_row.addWidget(self.mark_failed_button)
        top_row.addWidget(self.cancel_button)
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(SALE_HEADERS))
        self.table.setHorizontalHeaderLabels(SALE_HEADERS)
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
        sales = self._sale_service.list_sales(self._actor_user_id)
        self.table.setRowCount(len(sales))
        for row_index, sale in enumerate(sales):
            payment = self._sale_service.get_payment_for_sale(self._actor_user_id, sale.id)
            self.table.setItem(row_index, 0, QTableWidgetItem(sale.receipt_number))
            self.table.setItem(row_index, 1, QTableWidgetItem(sale.sale_at.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row_index, 2, QTableWidgetItem(sale.fuel.fuel_type if sale.fuel else ""))
            self.table.setItem(row_index, 3, QTableWidgetItem(f"{sale.quantity:g}"))
            self.table.setItem(row_index, 4, QTableWidgetItem(f"{sale.amount:g}"))
            self.table.setItem(row_index, 5, QTableWidgetItem(sale.payment_method.title()))
            self.table.setItem(row_index, 6, QTableWidgetItem(sale.status.title()))
            self.table.setItem(row_index, 7, QTableWidgetItem(payment.status.title() if payment else ""))
            self.table.item(row_index, 0).setData(Qt.UserRole, sale.id)
            self.table.item(row_index, 7).setData(Qt.UserRole, payment.id if payment else None)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = SaleFormDialog(
            self._sale_service, self._shift_service, self._employee_service,
            self._auth_service, self._actor_user_id, self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _cancel_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Cancel sale", "Select a sale to cancel first.")
            return
        sale_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)

        reason, ok = QInputDialog.getText(self, "Cancel sale", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._sale_service.cancel_sale(self._actor_user_id, sale_id, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not cancel sale", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not cancel sale", describe_unexpected_error(exc))
        self.refresh()

    def _mark_selected_payment_failed(self) -> None:
        self._act_on_selected_payment(
            "Mark payment failed", "Reason:", "Could not mark payment failed", self._sale_service.mark_payment_failed
        )

    def _refund_selected_payment(self) -> None:
        self._act_on_selected_payment(
            "Refund payment", "Reason:", "Could not refund payment", self._sale_service.refund_payment
        )

    def _act_on_selected_payment(self, title: str, prompt: str, error_title: str, action) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, title, "Select a sale to act on first.")
            return
        payment_id = self.table.item(rows[0].row(), 7).data(Qt.UserRole)
        if not payment_id:
            QMessageBox.information(self, title, "This sale has no payment record.")
            return

        reason, ok = QInputDialog.getText(self, title, prompt)
        if not ok or not reason.strip():
            return
        try:
            action(self._actor_user_id, payment_id, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, error_title, str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, error_title, describe_unexpected_error(exc))
        self.refresh()


class SaleFormDialog(QDialog):
    def __init__(self, sale_service, shift_service, employee_service, auth_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._sale_service = sale_service
        self._actor_user_id = actor_user_id
        self._self_service_assignment = None

        self.setWindowTitle("Record Sale")
        self.setMinimumWidth(400)

        self._can_pick_freely = auth_service.check_permission(actor_user_id, Permission.SHIFT_VIEW.value)

        form = QFormLayout()

        if self._can_pick_freely:
            self.shift_combo = QComboBox()
            for shift in shift_service.list_shifts(actor_user_id):
                if shift.status == "open":
                    self.shift_combo.addItem(f"{shift.shift_date} {shift.shift_label}", shift.id)

            self.nozzle_combo = QComboBox()
            for nozzle in shift_service.list_active_nozzles(actor_user_id):
                self.nozzle_combo.addItem(nozzle.code, nozzle.id)

            self.employee_combo = QComboBox()
            for employee in employee_service.list_employees(actor_user_id):
                self.employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

            form.addRow("Shift", self.shift_combo)
            form.addRow("Nozzle", self.nozzle_combo)
            form.addRow("Attendant", self.employee_combo)
        else:
            self._self_service_assignment = shift_service.get_my_active_assignment(actor_user_id)
            if self._self_service_assignment:
                nozzle = self._self_service_assignment.nozzle
                info = QLabel(f"Selling from your current assignment: {nozzle.code if nozzle else ''}")
            else:
                info = QLabel("You have no active nozzle assignment - ask a supervisor to assign you one first.")
            info.setObjectName("subtitle")
            info.setWordWrap(True)
            form.addRow(info)

        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setRange(0.01, 100_000)
        self.quantity_input.setDecimals(2)
        self.quantity_input.setValue(10)

        self.payment_combo = QComboBox()
        for method in PaymentMethod:
            self.payment_combo.addItem(method.value.title(), method)
        self.payment_combo.currentIndexChanged.connect(self._on_payment_method_changed)

        self.customer_combo = QComboBox()
        self.customer_combo.addItem("(none)", None)
        for customer in sale_service.list_customers(actor_user_id):
            if customer.status == StatusEnum.ACTIVE.value:
                self.customer_combo.addItem(customer.name, customer.id)
        self.customer_label = QLabel("Customer")

        self.reference_input = QLineEdit()
        self.reference_label = QLabel("UPI/Card reference")

        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)

        form.addRow("Quantity (L)", self.quantity_input)
        form.addRow("Payment method", self.payment_combo)
        form.addRow(self.customer_label, self.customer_combo)
        form.addRow(self.reference_label, self.reference_input)
        form.addRow("Remarks", self.remarks_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Record Sale")
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

        self._on_payment_method_changed()

    def _on_payment_method_changed(self) -> None:
        method = self.payment_combo.currentData()
        is_credit = method == PaymentMethod.CREDIT
        self.customer_combo.setVisible(True)
        self.customer_label.setText("Customer (required for credit)" if is_credit else "Customer")

        needs_reference = method in (PaymentMethod.UPI, PaymentMethod.CARD)
        self.reference_input.setVisible(needs_reference)
        self.reference_label.setVisible(needs_reference)

    def _save(self) -> None:
        self.error_label.hide()

        if self._can_pick_freely:
            if self.shift_combo.count() == 0:
                self._show_error("No open shifts available.")
                return
            if self.nozzle_combo.count() == 0:
                self._show_error("No active nozzles available.")
                return
            if self.employee_combo.count() == 0:
                self._show_error("No employees available.")
                return
            shift_id = self.shift_combo.currentData()
            nozzle_id = self.nozzle_combo.currentData()
            employee_id = self.employee_combo.currentData()
        elif self._self_service_assignment is not None:
            assignment = self._self_service_assignment
            shift_id = assignment.shift_id
            nozzle_id = assignment.nozzle_id
            employee_id = assignment.employee_id
        else:
            self._show_error("You have no active nozzle assignment.")
            return

        try:
            data = SaleCreate(
                shift_id=shift_id,
                nozzle_id=nozzle_id,
                employee_id=employee_id,
                quantity=Decimal(str(self.quantity_input.value())),
                payment_method=self.payment_combo.currentData(),
                customer_id=self.customer_combo.currentData(),
                reference_number=self.reference_input.text().strip() or None,
                remarks=self.remarks_input.text().strip() or None,
            )
            self._sale_service.create_sale(self._actor_user_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except ValueError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


class CustomersTab(QWidget):
    def __init__(self, sale_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._sale_service = sale_service
        self._actor_user_id = actor_user_id
        self._can_manage = can_manage

        self.add_button = QPushButton("+ Add Customer")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(CUSTOMER_HEADERS))
        self.table.setHorizontalHeaderLabels(CUSTOMER_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._toggle_selected_status)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        customers = self._sale_service.list_customers(self._actor_user_id)
        self.table.setRowCount(len(customers))
        for row_index, customer in enumerate(customers):
            self.table.setItem(row_index, 0, QTableWidgetItem(customer.name))
            self.table.setItem(row_index, 1, QTableWidgetItem(customer.phone or ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(customer.status.title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, customer.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = CustomerFormDialog(self._sale_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _toggle_selected_status(self) -> None:
        if not self._can_manage:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        customer_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        current_status = self.table.item(rows[0].row(), 2).text().lower()
        new_status = StatusEnum.INACTIVE if current_status == "active" else StatusEnum.ACTIVE

        reason, ok = QInputDialog.getText(self, "Change status", f"Reason to mark {new_status.value}:")
        if not ok or not reason.strip():
            return
        try:
            self._sale_service.set_customer_status(self._actor_user_id, customer_id, new_status, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not change status", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change status", describe_unexpected_error(exc))
        self.refresh()


class CustomerFormDialog(QDialog):
    def __init__(self, sale_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._sale_service = sale_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Add Customer")
        self.setMinimumWidth(360)

        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.address_input = QLineEdit()
        self.address_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(self.name_input, self.phone_input, self.email_input, self.address_input)

        form = QFormLayout()
        form.addRow("Name", self.name_input)
        form.addRow("Phone", self.phone_input)
        form.addRow("Email", self.email_input)
        form.addRow("Address", self.address_input)

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
            data = CustomerCreate(
                name=self.name_input.text(),
                phone=self.phone_input.text().strip() or None,
                email=self.email_input.text().strip() or None,
                address=self.address_input.text().strip() or None,
            )
            self._sale_service.create_customer(self._actor_user_id, data)
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
