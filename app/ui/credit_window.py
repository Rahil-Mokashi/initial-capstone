"""Credit Management UI (Phase 13). One tab: credit accounts, with a
per-customer statement dialog and payment/limit actions."""

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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import PaymentMethod, Permission
from app.core.exceptions import AppError
from app.services.report_export import export_table_excel, export_table_pdf
from app.schemas.credit import CreditAccountCreate, CustomerPaymentCreate
from app.ui.qt_utils import describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget

# Sentinel QComboBox data value for the "+ Add New Customer..." row -
# distinct from every real customer_id (a UUID string) so it can never
# collide with one, and distinct from None (used elsewhere for "no
# selection"/"(none)" rows) so it reads unambiguously as its own case.
_ADD_NEW_CUSTOMER = object()

ACCOUNT_HEADERS = ["Customer", "Credit Limit", "Outstanding", "Overdue", "Due (days)"]


class CreditWindow(QWidget):
    def __init__(self, credit_service, sale_service, auth_service, actor_user_id: str):
        super().__init__()
        self.setWindowTitle("Credit Management")
        self.setMinimumSize(820, 560)

        title = QLabel("Credit Management")
        title.setObjectName("title")

        can_manage = auth_service.check_permission(actor_user_id, Permission.CREDIT_MANAGE.value)
        self.accounts_tab = CreditAccountsTab(credit_service, sale_service, actor_user_id, can_manage)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(self.accounts_tab)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)


class CreditAccountsTab(QWidget):
    def __init__(self, credit_service, sale_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._credit_service = credit_service
        self._sale_service = sale_service
        self._actor_user_id = actor_user_id
        self._can_manage = can_manage

        self.open_button = QPushButton("+ Open Credit Account")
        self.open_button.setCursor(Qt.PointingHandCursor)
        self.open_button.clicked.connect(self._open_account_dialog)
        self.open_button.setVisible(can_manage)

        self.limit_button = QPushButton("Change Limit")
        self.limit_button.setObjectName("secondaryButton")
        self.limit_button.clicked.connect(self._change_selected_limit)
        self.limit_button.setVisible(can_manage)

        self.payment_button = QPushButton("Record Payment")
        self.payment_button.setObjectName("secondaryButton")
        self.payment_button.clicked.connect(self._record_selected_payment)
        self.payment_button.setVisible(can_manage)

        self.statement_button = QPushButton("View Statement")
        self.statement_button.setObjectName("secondaryButton")
        self.statement_button.clicked.connect(self._view_selected_statement)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.statement_button)
        top_row.addWidget(self.payment_button)
        top_row.addWidget(self.limit_button)
        top_row.addWidget(self.open_button)

        self.table = QTableWidget(0, len(ACCOUNT_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(ACCOUNT_HEADERS)
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
        accounts = self._credit_service.list_credit_accounts(self._actor_user_id)
        self.table.setRowCount(len(accounts))
        for row_index, account in enumerate(accounts):
            outstanding = self._credit_service.get_outstanding_balance(self._actor_user_id, account.customer_id)
            overdue = self._credit_service.is_overdue(self._actor_user_id, account.customer_id)
            self.table.setItem(row_index, 0, QTableWidgetItem(account.customer.name if account.customer else ""))
            self.table.setItem(row_index, 1, QTableWidgetItem(f"{account.credit_limit:g}"))
            self.table.setItem(row_index, 2, QTableWidgetItem(f"{outstanding:g}"))
            self.table.setItem(row_index, 3, QTableWidgetItem("Yes" if overdue else "No"))
            self.table.setItem(row_index, 4, QTableWidgetItem(str(account.payment_due_days)))
            self.table.item(row_index, 0).setData(Qt.UserRole, account.customer_id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _selected_customer_id(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def _open_account_dialog(self) -> None:
        dialog = CreditAccountFormDialog(self._credit_service, self._sale_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _change_selected_limit(self) -> None:
        customer_id = self._selected_customer_id()
        if not customer_id:
            QMessageBox.information(self, "Change limit", "Select a credit account first.")
            return

        new_limit, ok = QInputDialog.getDouble(self, "Change credit limit", "New limit:", 0, 0, 10_000_000, 2)
        if not ok:
            return
        reason, ok = QInputDialog.getText(self, "Change credit limit", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._credit_service.set_credit_limit(self._actor_user_id, customer_id, Decimal(str(new_limit)), reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not change limit", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change limit", describe_unexpected_error(exc))
        self.refresh()

    def _record_selected_payment(self) -> None:
        """No longer requires a row to be selected first - the dialog
        itself now carries a customer dropdown listing every credit
        account (see CustomerPaymentFormDialog). A selected row, if any,
        is still used to pre-fill that dropdown as a convenience."""
        dialog = CustomerPaymentFormDialog(
            self._credit_service, self._actor_user_id, self, initial_customer_id=self._selected_customer_id()
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _view_selected_statement(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "View statement", "Select a credit account first.")
            return
        customer_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        customer_name = self.table.item(rows[0].row(), 0).text()
        dialog = CustomerStatementDialog(self._credit_service, customer_id, self._actor_user_id, customer_name, self)
        dialog.exec()


class CreditAccountFormDialog(QDialog):
    def __init__(self, credit_service, sale_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._credit_service = credit_service
        self._sale_service = sale_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Open Credit Account")
        self.setMinimumWidth(360)

        self.customer_combo = QComboBox()
        for customer in sale_service.list_customers(actor_user_id):
            self.customer_combo.addItem(customer.name, customer.id)
        self.customer_combo.addItem("+ Add New Customer...", _ADD_NEW_CUSTOMER)
        self._previous_customer_index = 0
        # `activated` (not `currentIndexChanged`) - it fires every time the
        # user picks an item from the popup, even re-picking the one
        # already selected. That matters here because with zero real
        # customers, "+ Add New Customer..." is the only row and is
        # already selected by default; currentIndexChanged would never
        # fire again in that case since the index never actually changes.
        self.customer_combo.activated.connect(self._on_customer_combo_changed)

        self.limit_input = QDoubleSpinBox()
        self.limit_input.setRange(0.01, 10_000_000)
        self.limit_input.setDecimals(2)
        self.limit_input.setValue(10000)

        self.due_days_input = QSpinBox()
        self.due_days_input.setRange(1, 365)
        self.due_days_input.setValue(30)

        form = QFormLayout()
        form.addRow("Customer", self.customer_combo)
        form.addRow("Credit limit", self.limit_input)
        form.addRow("Payment due (days)", self.due_days_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Open Account")
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

    def _on_customer_combo_changed(self, index: int) -> None:
        """Picking "+ Add New Customer..." opens the same add-customer
        dialog the Sales screen uses (SaleService.create_customer is the
        one real place a Customer row gets created - this reuses it
        rather than a second, parallel customer-creation form), so a
        brand-new credit customer can be created without leaving this
        dialog. Cancelling, or the underlying save failing, reverts the
        combo to whatever was selected before rather than leaving the
        sentinel row selected as if it were a real customer.
        """
        if self.customer_combo.itemData(index) is not _ADD_NEW_CUSTOMER:
            self._previous_customer_index = index
            return

        from app.ui.sales_window import CustomerFormDialog

        dialog = CustomerFormDialog(self._sale_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted and dialog.created_customer is not None:
            customer = dialog.created_customer
            insert_at = self.customer_combo.count() - 1  # before the sentinel row
            self.customer_combo.insertItem(insert_at, customer.name, customer.id)
            self.customer_combo.setCurrentIndex(insert_at)
        else:
            self.customer_combo.setCurrentIndex(self._previous_customer_index)

    def _save(self) -> None:
        self.error_label.hide()
        if self.customer_combo.currentData() is _ADD_NEW_CUSTOMER:
            self._show_error("Choose a customer, or add a new one, first.")
            return
        try:
            data = CreditAccountCreate(
                customer_id=self.customer_combo.currentData(),
                credit_limit=Decimal(str(self.limit_input.value())),
                payment_due_days=self.due_days_input.value(),
            )
            self._credit_service.create_credit_account(self._actor_user_id, data)
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


class CustomerPaymentFormDialog(QDialog):
    """Record a payment against any credit customer.

    Used to require a row pre-selected in the accounts table before it
    could even be opened, with the customer baked in as a fixed
    constructor argument. Now carries its own customer dropdown (every
    customer who has a CreditAccount, per the same "record payment
    dropdown of existing customers" request), so it can be opened
    directly from the top-row "Record Payment" button with nothing
    selected - `initial_customer_id` just pre-fills the dropdown as a
    convenience when a row happens to be selected already.
    """

    def __init__(self, credit_service, actor_user_id: str, parent=None, initial_customer_id: str | None = None):
        super().__init__(parent)
        self._credit_service = credit_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Record Customer Payment")
        self.setMinimumWidth(360)

        self.customer_combo = QComboBox()
        for account in credit_service.list_credit_accounts(actor_user_id):
            if account.customer:
                self.customer_combo.addItem(account.customer.name, account.customer_id)
        if initial_customer_id is not None:
            index = self.customer_combo.findData(initial_customer_id)
            if index >= 0:
                self.customer_combo.setCurrentIndex(index)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.01, 10_000_000)
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(1000)

        self.method_combo = QComboBox()
        for method in PaymentMethod:
            if method != PaymentMethod.CREDIT:
                self.method_combo.addItem(method.value.title(), method)

        self.reference_input = QLineEdit()
        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)

        form = QFormLayout()
        form.addRow("Customer", self.customer_combo)
        form.addRow("Amount", self.amount_input)
        form.addRow("Method", self.method_combo)
        form.addRow("Reference", self.reference_input)
        form.addRow("Remarks", self.remarks_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Record Payment")
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
        if self.customer_combo.count() == 0:
            self._show_error("No credit accounts exist yet - open one first.")
            return
        try:
            data = CustomerPaymentCreate(
                customer_id=self.customer_combo.currentData(),
                amount=Decimal(str(self.amount_input.value())),
                payment_method=self.method_combo.currentData(),
                reference=self.reference_input.text().strip() or None,
                remarks=self.remarks_input.text().strip() or None,
            )
            self._credit_service.record_customer_payment(self._actor_user_id, data)
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


class CustomerStatementDialog(QDialog):
    def __init__(self, credit_service, customer_id: str, actor_user_id: str, customer_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customer Statement")
        self.setMinimumSize(560, 460)

        entries = credit_service.get_customer_statement(actor_user_id, customer_id)
        self._report = self._build_report(customer_name, entries)

        table = QTableWidget(len(entries), 4)
        table.setAlternatingRowColors(True)
        table.setHorizontalHeaderLabels(["Date", "Description", "Debit", "Credit"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        for row_index, entry in enumerate(entries):
            table.setItem(row_index, 0, QTableWidgetItem(entry.entry_date.strftime("%Y-%m-%d")))
            table.setItem(row_index, 1, QTableWidgetItem(entry.description))
            table.setItem(row_index, 2, QTableWidgetItem(f"{entry.debit:g}" if entry.debit else ""))
            table.setItem(row_index, 3, QTableWidgetItem(f"{entry.credit:g}" if entry.credit else ""))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)

        running_balance = entries[-1].running_balance if entries else Decimal("0")
        balance_label = QLabel(f"Running balance: {running_balance:g}")
        balance_label.setObjectName("subtitle")

        print_button = QPushButton("Print")
        print_button.setObjectName("secondaryButton")
        print_button.clicked.connect(self._print)

        export_excel_button = QPushButton("Export Excel")
        export_excel_button.setObjectName("secondaryButton")
        export_excel_button.clicked.connect(self._export_excel)

        export_pdf_button = QPushButton("Export PDF")
        export_pdf_button.setObjectName("secondaryButton")
        export_pdf_button.clicked.connect(self._export_pdf)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        button_row.addWidget(print_button)
        button_row.addWidget(export_excel_button)
        button_row.addWidget(export_pdf_button)
        button_row.addStretch()
        button_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.addWidget(table)
        layout.addWidget(balance_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    @staticmethod
    def _build_report(customer_name: str, entries):
        from app.services.report_service import TableReport

        rows = [
            [entry.entry_date.strftime("%Y-%m-%d"), entry.description, f"{entry.debit:.2f}" if entry.debit else "", f"{entry.credit:.2f}" if entry.credit else ""]
            for entry in entries
        ]
        running_balance = entries[-1].running_balance if entries else Decimal("0")
        rows.append(["", "Running Balance", "", f"{running_balance:.2f}"])
        title = f"Customer Statement - {customer_name}" if customer_name else "Customer Statement"
        return TableReport(title=title, headers=["Date", "Description", "Debit", "Credit"], rows=rows)

    def _print(self) -> None:
        from app.services.report_export import build_table_report_html
        from app.ui.print_utils import show_print_preview

        show_print_preview(build_table_report_html(self._report), self)

    def _export_pdf(self) -> None:
        self._export(export_table_pdf, "PDF Files (*.pdf)", ".pdf")

    def _export_excel(self) -> None:
        self._export(export_table_excel, "Excel Files (*.xlsx)", ".xlsx")

    def _export(self, export_fn, file_filter: str, default_suffix: str) -> None:
        from app.core.paths import default_export_path

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export statement", default_export_path(f"customer_statement{default_suffix}"), file_filter
        )
        if not file_path:
            return
        try:
            export_fn(self._report, file_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not export", describe_unexpected_error(exc))
            return
        QMessageBox.information(self, "Export complete", f"Statement saved to {file_path}")
