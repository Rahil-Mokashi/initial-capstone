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
    QFileDialog,
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
from app.database.base import StatusEnum
from app.schemas.customer import CustomerCreate
from app.schemas.sale import SaleCreate
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error, make_edit_icon_button
from app.ui.widgets import GridBackgroundWidget

# One screenful at a time. The sales table is the highest-volume list in
# the app - at 300 sales a day a pump reaches ~110,000 rows in a year, and
# every row becomes several native Qt objects on each refresh. Paging also
# bounds the per-row payment lookup below to the page size rather than the
# whole table.
SALES_PAGE_SIZE = 50

SALE_HEADERS = ["Receipt #", "When", "Fuel", "Quantity", "Amount", "Method", "Sale Status", "Payment Status"]
CUSTOMER_HEADERS = ["Name", "Phone", "Status", ""]


class SalesWindow(QWidget):
    def __init__(self, sale_service, shift_service, employee_service, auth_service, actor_user_id: str, report_service=None):
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

        # Today's per-fuel revenue cards - reuses ReportService.get_sales_report
        # (already fuel-type-sectioned, already SALE_VIEW-gated) rather than
        # re-aggregating sales in the UI, matching CLAUDE.md's "no business
        # logic in UI widgets" rule. report_service is optional (defaults to
        # None) so existing callers/tests that construct SalesWindow without
        # it keep working - the card row is simply skipped, same as a
        # permission gate hiding a section.
        self._report_service = report_service
        self._actor_user_id = actor_user_id
        self._fuel_cards_layout = QHBoxLayout()
        self._fuel_cards_layout.setSpacing(16)
        if report_service is not None:
            layout.addLayout(self._fuel_cards_layout)
            self._refresh_fuel_cards()

        layout.addWidget(tabs)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)

    def _refresh_fuel_cards(self) -> None:
        from datetime import date
        from decimal import Decimal

        while self._fuel_cards_layout.count():
            item = self._fuel_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        try:
            report = self._report_service.get_sales_report(self._actor_user_id, date.today(), date.today())
        except Exception:  # noqa: BLE001 - a broken card row must never block the whole screen
            return

        for row in report.rows:
            fuel_type, _count, quantity, amount = row
            if fuel_type == "Total":
                continue
            self._fuel_cards_layout.addWidget(_FuelRevenueCard(fuel_type, Decimal(quantity), Decimal(amount)))

        if not self._fuel_cards_layout.count():
            self._fuel_cards_layout.addWidget(_FuelRevenueCard("No sales today", Decimal("0"), Decimal("0")))


class _FuelRevenueCard(QWidget):
    """Today's liters + revenue for one fuel type - the reference design's
    "3 fuel-grade revenue cards" atop the Sales screen. Takes plain values
    rather than a report row so it stays independent of ReportService's
    exact row shape."""

    def __init__(self, fuel_type: str, quantity, amount, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        name_label = QLabel(fuel_type.upper())
        name_label.setObjectName("dashCardSubtitle")

        amount_label = QLabel(f"₹{amount:,.2f}")
        amount_label.setObjectName("statValue")

        quantity_label = QLabel(f"{quantity:g} L today")
        quantity_label.setObjectName("subtitle")

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)
        layout.addWidget(name_label)
        layout.addWidget(amount_label)
        layout.addWidget(quantity_label)
        self.setLayout(layout)

        from app.ui.qt_utils import apply_hard_shadow

        apply_hard_shadow(self)


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

        self.print_receipt_button = QPushButton("Print Receipt")
        self.print_receipt_button.setObjectName("secondaryButton")
        self.print_receipt_button.clicked.connect(self._print_selected_receipt)

        self.export_receipt_button = QPushButton("Export Receipt PDF")
        self.export_receipt_button.setObjectName("secondaryButton")
        self.export_receipt_button.clicked.connect(self._export_selected_receipt)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.export_receipt_button)
        top_row.addWidget(self.print_receipt_button)
        top_row.addWidget(self.refund_button)
        top_row.addWidget(self.mark_failed_button)
        top_row.addWidget(self.cancel_button)
        top_row.addWidget(self.add_button)

        self._page = 0

        self.prev_button = QPushButton("< Previous")
        self.prev_button.setObjectName("secondaryButton")
        self.prev_button.clicked.connect(self._previous_page)

        self.next_button = QPushButton("Next >")
        self.next_button.setObjectName("secondaryButton")
        self.next_button.clicked.connect(self._next_page)

        self.page_label = QLabel("")
        self.page_label.setObjectName("subtitle")

        pager_row = QHBoxLayout()
        pager_row.addWidget(self.prev_button)
        pager_row.addWidget(self.next_button)
        pager_row.addWidget(self.page_label)
        pager_row.addStretch()
        self._pager_row = pager_row

        self.table = QTableWidget(0, len(SALE_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(SALE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        layout.addLayout(self._pager_row)
        self.setLayout(layout)

        self.refresh()

    def _previous_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self.refresh()

    def _next_page(self) -> None:
        self._page += 1
        self.refresh()

    def refresh(self) -> None:
        total = self._sale_service.count_sales(self._actor_user_id)

        # Clamp: a deletion or a cancellation elsewhere can leave the
        # current page past the end, and showing an empty screen with no
        # way back would look like data loss.
        last_page = max((total - 1) // SALES_PAGE_SIZE, 0) if total else 0
        self._page = min(max(self._page, 0), last_page)

        offset = self._page * SALES_PAGE_SIZE
        sales = self._sale_service.list_sales(
            self._actor_user_id, limit=SALES_PAGE_SIZE, offset=offset
        )

        first = offset + 1 if sales else 0
        self.page_label.setText(
            f"Showing {first}-{offset + len(sales)} of {total}" if total else "No sales yet"
        )
        self.prev_button.setEnabled(self._page > 0)
        self.next_button.setEnabled(offset + len(sales) < total)

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

    def _print_selected_receipt(self) -> None:
        sale, payment = self._get_selected_sale_and_payment("Print receipt")
        if sale is None:
            return

        from app.services.report_export import build_sale_receipt_html
        from app.ui.print_utils import show_print_preview

        show_print_preview(build_sale_receipt_html(sale, payment), self)

    def _export_selected_receipt(self) -> None:
        sale, payment = self._get_selected_sale_and_payment("Export receipt")
        if sale is None:
            return

        from app.services.report_export import export_sale_receipt_pdf

        from app.core.paths import default_export_path

        default_name = f"receipt_{sale.receipt_number}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(self, "Export receipt", default_export_path(default_name), "PDF Files (*.pdf)")
        if not file_path:
            return

        try:
            export_sale_receipt_pdf(sale, payment, file_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not export receipt", describe_unexpected_error(exc))
            return

        QMessageBox.information(self, "Export complete", f"Receipt saved to {file_path}")

    def _get_selected_sale_and_payment(self, title: str):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, title, "Select a sale first.")
            return None, None
        sale_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)

        try:
            sale = self._sale_service.get_sale(self._actor_user_id, sale_id)
            payment = self._sale_service.get_payment_for_sale(self._actor_user_id, sale_id)
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, title, str(exc))
            return None, None
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, title, describe_unexpected_error(exc))
            return None, None

        return sale, payment

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
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(CUSTOMER_HEADERS)
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
        customers = self._sale_service.list_customers(self._actor_user_id)
        self.table.setRowCount(len(customers))
        for row_index, customer in enumerate(customers):
            self.table.setItem(row_index, 0, QTableWidgetItem(customer.name))
            self.table.setItem(row_index, 1, QTableWidgetItem(customer.phone or ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(customer.status.title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, customer.id)
            if self._can_manage:
                self.table.setCellWidget(
                    row_index, 3,
                    make_edit_icon_button(
                        lambda _=False, cid=customer.id: self._toggle_status(cid), tooltip="Change status"
                    ),
                )
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = CustomerFormDialog(self._sale_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _toggle_status(self, customer_id: str) -> None:
        if not self._can_manage:
            return
        current_status = None
        for row_index in range(self.table.rowCount()):
            if self.table.item(row_index, 0).data(Qt.UserRole) == customer_id:
                current_status = self.table.item(row_index, 2).text().lower()
                break
        if current_status is None:
            return
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
        self.created_customer = None  # set on successful save, so a caller (e.g. CreditAccountFormDialog) can select it immediately

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
            self.created_customer = self._sale_service.create_customer(self._actor_user_id, data)
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
