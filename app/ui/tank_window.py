"""Tank & Inventory UI (Phase 9). Pure presentation — validation and
business rules live in TankService and its Pydantic schemas.
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
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import Permission, TankStatus, TankTransactionType
from app.core.exceptions import AppError
from app.schemas.tank import ReconciliationPerform, TankCreate, TankReadingCreate, TankTransactionCreate
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error, qdate_to_date

TANK_HEADERS = ["Code", "Fuel", "Capacity", "Current Stock", "Status"]
TRANSACTION_HEADERS = ["Date", "Type", "Quantity", "Reference", "Recorded By"]
READING_HEADERS = ["Date", "Physical Stock", "Dip", "Employee"]
RECONCILIATION_HEADERS = ["Date", "Expected", "Physical", "Variance", "Classification"]


class TankListWindow(QMainWindow):
    def __init__(self, tank_service, employee_service, fuel_repo, auth_service, actor_user_id: str):
        super().__init__()
        self._tank_service = tank_service
        self._employee_service = employee_service
        self._fuel_repo = fuel_repo
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id
        self._can_manage = auth_service.check_permission(actor_user_id, Permission.INVENTORY_MANAGE.value)

        self.setWindowTitle("Tanks & Inventory")
        self.setMinimumSize(820, 560)

        title = QLabel("Tanks & Inventory")
        title.setObjectName("title")

        self.add_button = QPushButton("+ Add Tank")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(self._can_manage)

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(TANK_HEADERS))
        self.table.setHorizontalHeaderLabels(TANK_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._open_selected_tank)

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
        tanks = self._tank_service.list_tanks(self._actor_user_id)
        self.table.setRowCount(len(tanks))
        for row_index, tank in enumerate(tanks):
            self.table.setItem(row_index, 0, QTableWidgetItem(tank.code))
            self.table.setItem(row_index, 1, QTableWidgetItem(tank.fuel.fuel_type if tank.fuel else ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(f"{tank.capacity:g}"))
            self.table.setItem(row_index, 3, QTableWidgetItem(f"{tank.current_stock:g}"))
            self.table.setItem(row_index, 4, QTableWidgetItem(tank.status.title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, tank.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = TankFormDialog(self._tank_service, self._fuel_repo, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_selected_tank(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        tank_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        dialog = TankDetailDialog(
            self._tank_service, self._employee_service, self._auth_service, self._actor_user_id, tank_id, self
        )
        dialog.exec()
        self.refresh()


class TankFormDialog(QDialog):
    def __init__(self, tank_service, fuel_repo, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._tank_service = tank_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Add Tank")
        self.setMinimumWidth(360)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g. T1")

        self.fuel_combo = QComboBox()
        for fuel in fuel_repo.list_active():
            self.fuel_combo.addItem(fuel.fuel_type, fuel.id)

        self.capacity_input = QDoubleSpinBox()
        self.capacity_input.setRange(1, 1_000_000)
        self.capacity_input.setDecimals(2)
        self.capacity_input.setValue(10000.0)

        self.opening_stock_input = QDoubleSpinBox()
        self.opening_stock_input.setRange(0, 1_000_000)
        self.opening_stock_input.setDecimals(2)

        self.calibration_input = QLineEdit()
        self.calibration_input.setPlaceholderText("Optional calibration reference")
        self.calibration_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(
            self.code_input,
            self.fuel_combo,
            self.capacity_input,
            self.opening_stock_input,
            self.calibration_input,
        )

        form = QFormLayout()
        form.addRow("Code", self.code_input)
        form.addRow("Fuel type", self.fuel_combo)
        form.addRow("Capacity", self.capacity_input)
        form.addRow("Opening stock", self.opening_stock_input)
        form.addRow("Calibration info", self.calibration_input)

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
        if self.fuel_combo.count() == 0:
            self._show_error("No fuel types available.")
            return
        try:
            data = TankCreate(
                code=self.code_input.text(),
                fuel_id=self.fuel_combo.currentData(),
                capacity=self.capacity_input.value(),
                opening_stock=self.opening_stock_input.value(),
                calibration_info=self.calibration_input.text().strip() or None,
            )
            self._tank_service.create_tank(self._actor_user_id, data)
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


class TankDetailDialog(QDialog):
    def __init__(self, tank_service, employee_service, auth_service, actor_user_id: str, tank_id: str, parent=None):
        super().__init__(parent)
        self._tank_service = tank_service
        self._employee_service = employee_service
        self._actor_user_id = actor_user_id
        self._tank_id = tank_id
        self._can_manage = auth_service.check_permission(actor_user_id, Permission.INVENTORY_MANAGE.value)
        self._tank = tank_service.get_tank(actor_user_id, tank_id)

        self.setWindowTitle(f"Tank {self._tank.code}")
        self.setMinimumSize(640, 520)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("sectionTitle")

        self.receipt_button = QPushButton("Receipt")
        self.receipt_button.clicked.connect(lambda: self._open_transaction_dialog(TankTransactionType.RECEIPT))
        self.issue_button = QPushButton("Issue")
        self.issue_button.clicked.connect(lambda: self._open_transaction_dialog(TankTransactionType.ISSUE))
        self.adjustment_button = QPushButton("Adjustment")
        self.adjustment_button.setObjectName("secondaryButton")
        self.adjustment_button.clicked.connect(lambda: self._open_transaction_dialog(TankTransactionType.ADJUSTMENT))
        self.reading_button = QPushButton("Record Reading")
        self.reading_button.setObjectName("secondaryButton")
        self.reading_button.clicked.connect(self._open_reading_dialog)
        self.reconcile_button = QPushButton("Reconcile")
        self.reconcile_button.setObjectName("dangerButton")
        self.reconcile_button.clicked.connect(self._open_reconciliation_dialog)
        self.status_button = QPushButton("Change Status")
        self.status_button.setObjectName("secondaryButton")
        self.status_button.clicked.connect(self._change_status)

        for button in (
            self.receipt_button, self.issue_button, self.adjustment_button,
            self.reading_button, self.reconcile_button, self.status_button,
        ):
            button.setEnabled(self._can_manage)

        action_row = QHBoxLayout()
        action_row.addWidget(self.receipt_button)
        action_row.addWidget(self.issue_button)
        action_row.addWidget(self.adjustment_button)
        action_row.addWidget(self.reading_button)
        action_row.addWidget(self.reconcile_button)
        action_row.addWidget(self.status_button)

        self.transactions_table = self._make_table(TRANSACTION_HEADERS)
        self.readings_table = self._make_table(READING_HEADERS)
        self.reconciliations_table = self._make_table(RECONCILIATION_HEADERS)

        tabs = QTabWidget()
        tabs.addTab(self.transactions_table, "Transactions")
        tabs.addTab(self.readings_table, "Readings")
        tabs.addTab(self.reconciliations_table, "Reconciliation")

        close_button = QPushButton("Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.accept)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.addWidget(self.summary_label)
        layout.addLayout(action_row)
        layout.addWidget(tabs)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

        self._refresh()

    def _make_table(self, headers) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _refresh(self) -> None:
        self._tank = self._tank_service.get_tank(self._actor_user_id, self._tank_id)
        self.summary_label.setText(
            f"{self._tank.code} — {self._tank.fuel.fuel_type if self._tank.fuel else ''} — "
            f"{self._tank.current_stock:g} / {self._tank.capacity:g} — {self._tank.status.title()}"
        )

        transactions = self._tank_service.list_transactions(self._actor_user_id, self._tank_id)
        self.transactions_table.setRowCount(len(transactions))
        for row_index, txn in enumerate(transactions):
            self.transactions_table.setItem(row_index, 0, QTableWidgetItem(txn.transaction_at.strftime("%Y-%m-%d %H:%M")))
            self.transactions_table.setItem(row_index, 1, QTableWidgetItem(txn.transaction_type.title()))
            self.transactions_table.setItem(row_index, 2, QTableWidgetItem(f"{txn.quantity:+g}"))
            self.transactions_table.setItem(row_index, 3, QTableWidgetItem(txn.reference or ""))
            self.transactions_table.setItem(row_index, 4, QTableWidgetItem(txn.recorded_by.username if txn.recorded_by else ""))
        self.transactions_table.resizeColumnsToContents()

        readings = self._tank_service.list_readings(self._actor_user_id, self._tank_id)
        self.readings_table.setRowCount(len(readings))
        for row_index, reading in enumerate(readings):
            self.readings_table.setItem(row_index, 0, QTableWidgetItem(reading.reading_at.strftime("%Y-%m-%d %H:%M")))
            self.readings_table.setItem(row_index, 1, QTableWidgetItem(f"{reading.physical_stock:g}"))
            self.readings_table.setItem(row_index, 2, QTableWidgetItem(f"{reading.dip_value:g}" if reading.dip_value is not None else ""))
            self.readings_table.setItem(row_index, 3, QTableWidgetItem(f"{reading.employee.first_name} {reading.employee.last_name}" if reading.employee else ""))
        self.readings_table.resizeColumnsToContents()

        reconciliations = self._tank_service.list_reconciliations(self._actor_user_id, self._tank_id)
        self.reconciliations_table.setRowCount(len(reconciliations))
        for row_index, rec in enumerate(reconciliations):
            self.reconciliations_table.setItem(row_index, 0, QTableWidgetItem(rec.reconciliation_date.isoformat()))
            self.reconciliations_table.setItem(row_index, 1, QTableWidgetItem(f"{rec.expected_closing_stock:g}"))
            self.reconciliations_table.setItem(row_index, 2, QTableWidgetItem(f"{rec.physical_stock:g}"))
            self.reconciliations_table.setItem(row_index, 3, QTableWidgetItem(f"{rec.variance:+g}"))
            self.reconciliations_table.setItem(row_index, 4, QTableWidgetItem(rec.classification.replace("_", " ").title()))
        self.reconciliations_table.resizeColumnsToContents()

    def _open_transaction_dialog(self, transaction_type: TankTransactionType) -> None:
        dialog = TankTransactionDialog(self._tank_service, self._actor_user_id, self._tank_id, transaction_type, self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh()

    def _open_reading_dialog(self) -> None:
        dialog = TankReadingDialog(self._tank_service, self._employee_service, self._actor_user_id, self._tank_id, self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh()

    def _open_reconciliation_dialog(self) -> None:
        dialog = ReconciliationDialog(self._tank_service, self._actor_user_id, self._tank_id, self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh()

    def _change_status(self) -> None:
        status_names = [s.value for s in TankStatus]
        new_status_name, ok = QInputDialog.getItem(self, "Change status", "New status:", status_names, editable=False)
        if not ok:
            return
        reason, ok = QInputDialog.getText(self, "Change status", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._tank_service.set_tank_status(self._actor_user_id, self._tank_id, TankStatus(new_status_name), reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not change status", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change status", describe_unexpected_error(exc))
        self._refresh()


class TankTransactionDialog(QDialog):
    def __init__(self, tank_service, actor_user_id: str, tank_id: str, transaction_type: TankTransactionType, parent=None):
        super().__init__(parent)
        self._tank_service = tank_service
        self._actor_user_id = actor_user_id
        self._tank_id = tank_id
        self._transaction_type = transaction_type

        self.setWindowTitle(f"Record {transaction_type.value.title()}")
        self.setMinimumWidth(360)

        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setRange(-1_000_000, 1_000_000)
        self.quantity_input.setDecimals(2)
        if transaction_type != TankTransactionType.ADJUSTMENT:
            self.quantity_input.setRange(0.01, 1_000_000)

        self.reference_input = QLineEdit()
        self.reference_input.setPlaceholderText("Optional reference (invoice #, etc.)")

        self.remarks_input = QLineEdit()
        if transaction_type == TankTransactionType.ADJUSTMENT:
            self.remarks_input.setPlaceholderText("Reason (required)")
        self.remarks_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(self.quantity_input, self.reference_input, self.remarks_input)

        form = QFormLayout()
        form.addRow("Quantity", self.quantity_input)
        form.addRow("Reference", self.reference_input)
        form.addRow("Remarks", self.remarks_input)

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
            data = TankTransactionCreate(
                quantity=self.quantity_input.value(),
                reference=self.reference_input.text().strip() or None,
                remarks=self.remarks_input.text().strip() or None,
            )
            self._tank_service.record_transaction(self._actor_user_id, self._tank_id, self._transaction_type, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except (AppError, ValueError) as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


class TankReadingDialog(QDialog):
    def __init__(self, tank_service, employee_service, actor_user_id: str, tank_id: str, parent=None):
        super().__init__(parent)
        self._tank_service = tank_service
        self._actor_user_id = actor_user_id
        self._tank_id = tank_id

        self.setWindowTitle("Record Tank Reading")
        self.setMinimumWidth(360)

        self.employee_combo = QComboBox()
        for employee in employee_service.list_employees(actor_user_id):
            self.employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

        self.physical_stock_input = QDoubleSpinBox()
        self.physical_stock_input.setRange(0, 1_000_000)
        self.physical_stock_input.setDecimals(2)

        self.dip_value_input = QDoubleSpinBox()
        self.dip_value_input.setRange(0, 10_000)
        self.dip_value_input.setDecimals(2)

        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)

        form = QFormLayout()
        form.addRow("Employee", self.employee_combo)
        form.addRow("Physical stock", self.physical_stock_input)
        form.addRow("Dip value", self.dip_value_input)
        form.addRow("Remarks", self.remarks_input)

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
            self._show_error("No employees available.")
            return
        try:
            data = TankReadingCreate(
                employee_id=self.employee_combo.currentData(),
                physical_stock=self.physical_stock_input.value(),
                dip_value=self.dip_value_input.value() or None,
                remarks=self.remarks_input.text().strip() or None,
            )
            self._tank_service.record_reading(self._actor_user_id, self._tank_id, data)
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


class ReconciliationDialog(QDialog):
    def __init__(self, tank_service, actor_user_id: str, tank_id: str, parent=None):
        super().__init__(parent)
        self._tank_service = tank_service
        self._actor_user_id = actor_user_id
        self._tank_id = tank_id

        self.setWindowTitle("Perform Reconciliation")
        self.setMinimumWidth(360)

        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)

        self.physical_stock_input = QDoubleSpinBox()
        self.physical_stock_input.setRange(0, 1_000_000)
        self.physical_stock_input.setDecimals(2)

        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)

        form = QFormLayout()
        form.addRow("Date", self.date_input)
        form.addRow("Physical stock", self.physical_stock_input)
        form.addRow("Remarks", self.remarks_input)

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
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        try:
            data = ReconciliationPerform(
                reconciliation_date=qdate_to_date(self.date_input.date()),
                physical_stock=self.physical_stock_input.value(),
                remarks=self.remarks_input.text().strip() or None,
            )
            result = self._tank_service.perform_reconciliation(self._actor_user_id, self._tank_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        QMessageBox.information(
            self,
            "Reconciliation complete",
            f"Variance: {result.variance:+g} ({result.variance_percent:+.2f}%)\n"
            f"Classification: {result.classification.replace('_', ' ').title()}",
        )
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
