"""Shift Reconciliation UI (Phase 15). One tab: reconciliations.

Reshaped for per-tender lines (PROJECT_CONTEXT.md's Step 2): the form
dialog no longer has three fixed cash/UPI/card inputs - it asks
ReconciliationService which tenders actually had expected activity for
the chosen shift, then builds one declared-amount input per tender
dynamically, since that set varies shift to shift (a typical shift
today still shows ~3 - Cash, Card, Other - but a future shift with a
DTP Card sale would show a fourth, with no code change needed).
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
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import Permission
from app.core.exceptions import AppError
from app.schemas.employee_cash_shortage import EmployeeCashShortageRecord, EmployeeShortageRecoveryRecord
from app.schemas.shift_cash_book import ShiftBankDepositRecord, ShiftCashBookRecord
from app.schemas.shift_reconciliation import ShiftReconciliationPerform
from app.ui.qt_utils import describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget

RECONCILIATION_HEADERS = ["Shift", "Variance by Tender", "Classification", "Status"]
CASH_BOOK_HEADERS = [
    "Shift",
    "Opening Balance",
    "Advance",
    "Final",
    "Bank Deposits",
    "Closing Cash-in-Hand",
    "Recorded By",
]
SHORTAGE_HEADERS = ["Employee", "Shift", "Tender", "Amount", "Recovered", "Outstanding", "Status"]


class ReconciliationWindow(QWidget):
    def __init__(
        self,
        reconciliation_service,
        shift_service,
        auth_service,
        actor_user_id: str,
        cash_book_service=None,
        employee_shortage_service=None,
        employee_service=None,
    ):
        super().__init__()
        self.setWindowTitle("Shift Reconciliation")
        self.setMinimumSize(880, 700)

        title = QLabel("Shift Reconciliation")
        title.setObjectName("title")

        can_manage = auth_service.check_permission(actor_user_id, Permission.RECONCILIATION_MANAGE.value)
        can_approve = auth_service.check_permission(actor_user_id, Permission.RECONCILIATION_APPROVE.value)
        self.reconciliations_tab = ReconciliationsTab(
            reconciliation_service, shift_service, auth_service, actor_user_id, can_manage, can_approve
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(self.reconciliations_tab)

        # Optional: main_window.py always wires this, but a test or an
        # older caller can still build a reconciliation-only screen.
        if cash_book_service is not None:
            cash_book_title = QLabel("Shift Cash Custody (Advance / Final)")
            cash_book_title.setObjectName("sectionTitle")
            self.cash_book_tab = CashBookTab(cash_book_service, shift_service, auth_service, actor_user_id, can_manage)
            layout.addWidget(cash_book_title)
            layout.addWidget(self.cash_book_tab)

        # Optional, same reasoning as cash_book_service above.
        if employee_shortage_service is not None:
            can_manage_shortages = auth_service.check_permission(actor_user_id, Permission.SHORTAGE_MANAGE.value)
            shortages_title = QLabel("Employee Cash Shortages")
            shortages_title.setObjectName("sectionTitle")
            self.shortages_tab = EmployeeShortagesTab(
                employee_shortage_service, employee_service, shift_service, actor_user_id, can_manage_shortages,
            )
            layout.addWidget(shortages_title)
            layout.addWidget(self.shortages_tab)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)


class ReconciliationsTab(QWidget):
    def __init__(self, reconciliation_service, shift_service, auth_service, actor_user_id: str, can_manage: bool, can_approve: bool):
        super().__init__()
        self._reconciliation_service = reconciliation_service
        self._shift_service = shift_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id

        self.add_button = QPushButton("+ Reconcile Shift")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        self.approve_button = QPushButton("Approve Selected")
        self.approve_button.setObjectName("secondaryButton")
        self.approve_button.clicked.connect(self._approve_selected)
        self.approve_button.setVisible(can_approve)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.approve_button)
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(RECONCILIATION_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(RECONCILIATION_HEADERS)
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
        reconciliations = self._reconciliation_service.list_reconciliations(self._actor_user_id)
        self.table.setRowCount(len(reconciliations))
        for row_index, recon in enumerate(reconciliations):
            shift_label = f"{recon.shift.shift_date} {recon.shift.shift_label}" if recon.shift else ""
            variance_summary = ", ".join(
                f"{line.tender.name}: {line.variance:+.2f}" for line in recon.lines if line.tender
            ) or "No tenders had activity"
            self.table.setItem(row_index, 0, QTableWidgetItem(shift_label))
            self.table.setItem(row_index, 1, QTableWidgetItem(variance_summary))
            self.table.setItem(row_index, 2, QTableWidgetItem(recon.classification.replace("_", " ").title()))
            self.table.setItem(row_index, 3, QTableWidgetItem(recon.status.replace("_", " ").title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, recon.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = ReconciliationFormDialog(self._reconciliation_service, self._shift_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _approve_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Approve reconciliation", "Select a reconciliation to approve first.")
            return
        reconciliation_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)

        remarks, ok = QInputDialog.getText(self, "Approve reconciliation", "Remarks (optional):")
        if not ok:
            return
        try:
            self._reconciliation_service.approve_shift_reconciliation(self._actor_user_id, reconciliation_id, remarks.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not approve reconciliation", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not approve reconciliation", describe_unexpected_error(exc))
        self.refresh()


class ReconciliationFormDialog(QDialog):
    def __init__(self, reconciliation_service, shift_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._reconciliation_service = reconciliation_service
        self._actor_user_id = actor_user_id
        self._tender_inputs: dict = {}  # tender_id -> QDoubleSpinBox

        self.setWindowTitle("Reconcile Shift")
        self.setMinimumWidth(420)

        self.shift_combo = QComboBox()
        for shift in shift_service.list_shifts(actor_user_id):
            self.shift_combo.addItem(f"{shift.shift_date} {shift.shift_label} ({shift.status})", shift.id)
        self.shift_combo.currentIndexChanged.connect(self._reload_tender_inputs)

        self.top_form = QFormLayout()
        self.top_form.addRow("Shift", self.shift_combo)

        # Rebuilt every time the selected shift changes - see
        # _reload_tender_inputs. A dedicated layout so it can be cleared
        # and repopulated without touching top_form/bottom_form.
        self.tender_form = QFormLayout()

        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)
        self.bottom_form = QFormLayout()
        self.bottom_form.addRow("Remarks", self.remarks_input)

        self.no_activity_label = QLabel("This shift has no reconcilable tender activity.")
        self.no_activity_label.setWordWrap(True)
        self.no_activity_label.hide()

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Reconcile")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(self.top_form)
        layout.addLayout(self.tender_form)
        layout.addWidget(self.no_activity_label)
        layout.addLayout(self.bottom_form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

        self._reload_tender_inputs()

    def _clear_tender_inputs(self) -> None:
        while self.tender_form.rowCount():
            self.tender_form.removeRow(0)
        self._tender_inputs = {}

    def _reload_tender_inputs(self) -> None:
        self.error_label.hide()
        self._clear_tender_inputs()
        if self.shift_combo.count() == 0:
            self.no_activity_label.show()
            return

        shift_id = self.shift_combo.currentData()
        try:
            expected_amounts = self._reconciliation_service.get_expected_amounts_for_shift(self._actor_user_id, shift_id)
        except AppError as exc:
            self._show_error(str(exc))
            return

        self.no_activity_label.setVisible(len(expected_amounts) == 0)
        for tender, expected in sorted(expected_amounts, key=lambda pair: pair[0].name):
            spin = QDoubleSpinBox()
            spin.setRange(0, 10_000_000)
            spin.setDecimals(2)
            self.tender_form.addRow(f"Declared {tender.name} (expected {expected:.2f})", spin)
            self._tender_inputs[tender.id] = spin

    def _save(self) -> None:
        self.error_label.hide()
        if self.shift_combo.count() == 0:
            self._show_error("No shifts available.")
            return
        try:
            data = ShiftReconciliationPerform(
                shift_id=self.shift_combo.currentData(),
                declared_amounts={
                    tender_id: Decimal(str(spin.value())) for tender_id, spin in self._tender_inputs.items()
                },
                remarks=self.remarks_input.text().strip() or None,
            )
            self._reconciliation_service.perform_shift_reconciliation(self._actor_user_id, data)
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


class CashBookTab(QWidget):
    """Records Advance/Final custody transfers per shift (PROJECT_CONTEXT.md
    Step 3, A1). Opening balance / bank deposits / derived closing
    cash-in-hand are Step 4 - this only records the two figures Step 4
    builds the rest of the cash book on top of."""

    def __init__(self, cash_book_service, shift_service, auth_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._cash_book_service = cash_book_service
        self._shift_service = shift_service
        self._actor_user_id = actor_user_id

        self.add_button = QPushButton("+ Record Cash Movements")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        self.deposit_button = QPushButton("+ Record Bank Deposit")
        self.deposit_button.setCursor(Qt.PointingHandCursor)
        self.deposit_button.clicked.connect(self._open_deposit_dialog)
        self.deposit_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.deposit_button)
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(CASH_BOOK_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(CASH_BOOK_HEADERS)
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
        cash_books = self._cash_book_service.list_all(self._actor_user_id)
        self.table.setRowCount(len(cash_books))
        for row_index, cb in enumerate(cash_books):
            shift_label = f"{cb.shift.shift_date} {cb.shift.shift_label}" if cb.shift else ""
            recorded_by = cb.recorded_by.username if cb.recorded_by else ""
            # opening_balance and closing_cash_in_hand are never columns on
            # ShiftCashBook - they are recomputed here on every refresh from
            # the previous shift's own cash book plus this shift's bank
            # deposits (ShiftCashBookService.get_cash_book_summary), the
            # same "recompute rather than store and drift" rule this
            # project already applies to CreditAccount's outstanding
            # balance and PurchaseOrder.status.
            summary = self._cash_book_service.get_cash_book_summary(self._actor_user_id, cb.shift_id)
            self.table.setItem(row_index, 0, QTableWidgetItem(shift_label))
            self.table.setItem(row_index, 1, QTableWidgetItem(f"{summary.opening_balance:.2f}"))
            self.table.setItem(row_index, 2, QTableWidgetItem(f"{cb.advance_amount:.2f}"))
            self.table.setItem(row_index, 3, QTableWidgetItem(f"{cb.final_amount:.2f}"))
            self.table.setItem(row_index, 4, QTableWidgetItem(f"{summary.bank_deposits_total:.2f}"))
            self.table.setItem(row_index, 5, QTableWidgetItem(f"{summary.closing_cash_in_hand:.2f}"))
            self.table.setItem(row_index, 6, QTableWidgetItem(recorded_by))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = CashBookFormDialog(self._cash_book_service, self._shift_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_deposit_dialog(self) -> None:
        dialog = BankDepositFormDialog(self._cash_book_service, self._shift_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()


class CashBookFormDialog(QDialog):
    def __init__(self, cash_book_service, shift_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._cash_book_service = cash_book_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Record Shift Cash Movements")
        self.setMinimumWidth(400)

        self.shift_combo = QComboBox()
        for shift in shift_service.list_shifts(actor_user_id):
            self.shift_combo.addItem(f"{shift.shift_date} {shift.shift_label} ({shift.status})", shift.id)

        self.advance_input = QDoubleSpinBox()
        self.advance_input.setRange(0, 10_000_000)
        self.advance_input.setDecimals(2)

        self.final_input = QDoubleSpinBox()
        self.final_input.setRange(0, 10_000_000)
        self.final_input.setDecimals(2)

        form = QFormLayout()
        form.addRow("Shift", self.shift_combo)
        form.addRow("Advance handed over", self.advance_input)
        form.addRow("Final handed over", self.final_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Record")
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
        if self.shift_combo.count() == 0:
            self._show_error("No shifts available.")
            return
        try:
            data = ShiftCashBookRecord(
                shift_id=self.shift_combo.currentData(),
                advance_amount=Decimal(str(self.advance_input.value())),
                final_amount=Decimal(str(self.final_input.value())),
            )
            self._cash_book_service.record_shift_cash_movements(self._actor_user_id, data)
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


class BankDepositFormDialog(QDialog):
    """Records one named bank deposit against a shift's cash book
    (PROJECT_CONTEXT.md Step 4). Only shifts with a cash book already
    recorded are offered - a deposit is a payment out of that cash
    book, so there must be one to pay out of."""

    def __init__(self, cash_book_service, shift_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._cash_book_service = cash_book_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Record Bank Deposit")
        self.setMinimumWidth(400)

        self.shift_combo = QComboBox()
        cash_books = cash_book_service.list_all(actor_user_id)
        for cb in cash_books:
            label = f"{cb.shift.shift_date} {cb.shift.shift_label}" if cb.shift else cb.shift_id
            self.shift_combo.addItem(label, cb.shift_id)

        self.bank_name_input = QLineEdit()
        self.bank_name_input.setPlaceholderText("e.g. HDFC Bank")

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0, 10_000_000)
        self.amount_input.setDecimals(2)

        form = QFormLayout()
        form.addRow("Shift", self.shift_combo)
        form.addRow("Bank", self.bank_name_input)
        form.addRow("Amount deposited", self.amount_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Record")
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
        if self.shift_combo.count() == 0:
            self._show_error("No shifts with recorded cash movements yet.")
            return
        try:
            data = ShiftBankDepositRecord(
                shift_id=self.shift_combo.currentData(),
                bank_name=self.bank_name_input.text(),
                amount=Decimal(str(self.amount_input.value())),
            )
            self._cash_book_service.record_bank_deposit(self._actor_user_id, data)
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


class EmployeeShortagesTab(QWidget):
    """A cash shortage found at reconciliation, and its recovery
    (PROJECT_CONTEXT.md Step 5, A2). Booking a shortage names which
    employee is responsible - a human judgement call, not something
    this screen derives on its own - and books the Expense side of it
    automatically (EmployeeShortageService.record_shortage). Outstanding
    is always recomputed from the shortage's own recoveries, never
    stored (see EmployeeCashShortage's docstring)."""

    def __init__(self, employee_shortage_service, employee_service, shift_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._employee_shortage_service = employee_shortage_service
        self._employee_service = employee_service
        self._shift_service = shift_service
        self._actor_user_id = actor_user_id

        self.add_shortage_button = QPushButton("+ Record Shortage")
        self.add_shortage_button.setCursor(Qt.PointingHandCursor)
        self.add_shortage_button.clicked.connect(self._open_shortage_dialog)
        self.add_shortage_button.setVisible(can_manage)

        self.add_recovery_button = QPushButton("+ Record Recovery")
        self.add_recovery_button.setCursor(Qt.PointingHandCursor)
        self.add_recovery_button.clicked.connect(self._open_recovery_dialog)
        self.add_recovery_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.add_recovery_button)
        top_row.addWidget(self.add_shortage_button)

        self.table = QTableWidget(0, len(SHORTAGE_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(SHORTAGE_HEADERS)
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
        shortages = self._employee_shortage_service.list_all(self._actor_user_id)
        self.table.setRowCount(len(shortages))
        for row_index, shortage in enumerate(shortages):
            employee = shortage.employee
            employee_label = f"{employee.first_name} {employee.last_name}" if employee else ""
            line = shortage.shift_reconciliation_line
            shift = line.shift_reconciliation.shift if line and line.shift_reconciliation else None
            shift_label = f"{shift.shift_date} {shift.shift_label}" if shift else ""
            tender_label = line.tender.name if line and line.tender else ""
            outstanding = self._employee_shortage_service.get_outstanding_balance(self._actor_user_id, shortage.id)
            recovered = shortage.amount - outstanding
            status = "Recovered" if outstanding <= 0 else "Outstanding"

            self.table.setItem(row_index, 0, QTableWidgetItem(employee_label))
            self.table.setItem(row_index, 1, QTableWidgetItem(shift_label))
            self.table.setItem(row_index, 2, QTableWidgetItem(tender_label))
            self.table.setItem(row_index, 3, QTableWidgetItem(f"{shortage.amount:.2f}"))
            self.table.setItem(row_index, 4, QTableWidgetItem(f"{recovered:.2f}"))
            self.table.setItem(row_index, 5, QTableWidgetItem(f"{outstanding:.2f}"))
            self.table.setItem(row_index, 6, QTableWidgetItem(status))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_shortage_dialog(self) -> None:
        dialog = RecordShortageDialog(
            self._employee_shortage_service, self._employee_service, self._actor_user_id, self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_recovery_dialog(self) -> None:
        dialog = RecordRecoveryDialog(
            self._employee_shortage_service, self._shift_service, self._actor_user_id, self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh()


class RecordShortageDialog(QDialog):
    def __init__(self, employee_shortage_service, employee_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._employee_shortage_service = employee_shortage_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Record Cash Shortage")
        self.setMinimumWidth(440)

        self.line_combo = QComboBox()
        for line in employee_shortage_service.list_unbooked_shortage_lines(actor_user_id):
            shift = line.shift_reconciliation.shift if line.shift_reconciliation else None
            shift_label = f"{shift.shift_date} {shift.shift_label}" if shift else line.shift_reconciliation_id
            tender_name = line.tender.name if line.tender else ""
            label = f"{shift_label} - {tender_name} short {abs(line.variance):.2f}"
            self.line_combo.addItem(label, line.id)

        self.employee_combo = QComboBox()
        for employee in employee_service.list_employees(actor_user_id):
            self.employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Optional notes")

        form = QFormLayout()
        form.addRow("Reconciliation line", self.line_combo)
        form.addRow("Responsible employee", self.employee_combo)
        form.addRow("Notes", self.notes_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Record")
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
        if self.line_combo.count() == 0:
            self._show_error("No unbooked cash shortages to record.")
            return
        if self.employee_combo.count() == 0:
            self._show_error("No employees available.")
            return
        try:
            data = EmployeeCashShortageRecord(
                shift_reconciliation_line_id=self.line_combo.currentData(),
                employee_id=self.employee_combo.currentData(),
                notes=self.notes_input.text().strip() or None,
            )
            self._employee_shortage_service.record_shortage(self._actor_user_id, data)
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


class RecordRecoveryDialog(QDialog):
    def __init__(self, employee_shortage_service, shift_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._employee_shortage_service = employee_shortage_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Record Shortage Recovery")
        self.setMinimumWidth(400)

        self.shortage_combo = QComboBox()
        for shortage in employee_shortage_service.list_all(actor_user_id):
            outstanding = employee_shortage_service.get_outstanding_balance(actor_user_id, shortage.id)
            if outstanding <= 0:
                continue
            employee = shortage.employee
            employee_label = f"{employee.first_name} {employee.last_name}" if employee else shortage.employee_id
            label = f"{employee_label} - outstanding {outstanding:.2f}"
            self.shortage_combo.addItem(label, shortage.id)

        # Which shift's cash book physically receives this repayment -
        # not necessarily the shift the shortage was found in (see
        # EmployeeShortageRecovery's own docstring). That shift must
        # already have its cash book recorded (Advance/Final), the same
        # requirement a bank deposit has.
        self.shift_combo = QComboBox()
        for shift in shift_service.list_shifts(actor_user_id):
            self.shift_combo.addItem(f"{shift.shift_date} {shift.shift_label} ({shift.status})", shift.id)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0, 10_000_000)
        self.amount_input.setDecimals(2)

        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Optional notes")

        form = QFormLayout()
        form.addRow("Shortage", self.shortage_combo)
        form.addRow("Repaid into shift", self.shift_combo)
        form.addRow("Amount recovered", self.amount_input)
        form.addRow("Notes", self.notes_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Record")
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
        if self.shortage_combo.count() == 0:
            self._show_error("No outstanding shortages to record a recovery against.")
            return
        if self.shift_combo.count() == 0:
            self._show_error("No shifts available.")
            return
        try:
            data = EmployeeShortageRecoveryRecord(
                employee_cash_shortage_id=self.shortage_combo.currentData(),
                shift_id=self.shift_combo.currentData(),
                amount=Decimal(str(self.amount_input.value())),
                notes=self.notes_input.text().strip() or None,
            )
            self._employee_shortage_service.record_recovery(self._actor_user_id, data)
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
