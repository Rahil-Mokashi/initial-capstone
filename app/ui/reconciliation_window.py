"""Shift Reconciliation UI (Phase 15). One tab: reconciliations."""

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
from app.schemas.shift_reconciliation import ShiftReconciliationPerform
from app.ui.qt_utils import describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget

RECONCILIATION_HEADERS = ["Shift", "Cash Var.", "UPI Var.", "Card Var.", "Classification", "Status"]


class ReconciliationWindow(QWidget):
    def __init__(self, reconciliation_service, shift_service, auth_service, actor_user_id: str):
        super().__init__()
        self.setWindowTitle("Shift Reconciliation")
        self.setMinimumSize(880, 600)

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
            self.table.setItem(row_index, 0, QTableWidgetItem(shift_label))
            self.table.setItem(row_index, 1, QTableWidgetItem(f"{recon.cash_variance:g}"))
            self.table.setItem(row_index, 2, QTableWidgetItem(f"{recon.upi_variance:g}"))
            self.table.setItem(row_index, 3, QTableWidgetItem(f"{recon.card_variance:g}"))
            self.table.setItem(row_index, 4, QTableWidgetItem(recon.classification.replace("_", " ").title()))
            self.table.setItem(row_index, 5, QTableWidgetItem(recon.status.replace("_", " ").title()))
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

        self.setWindowTitle("Reconcile Shift")
        self.setMinimumWidth(400)

        self.shift_combo = QComboBox()
        for shift in shift_service.list_shifts(actor_user_id):
            self.shift_combo.addItem(f"{shift.shift_date} {shift.shift_label} ({shift.status})", shift.id)

        self.cash_input = QDoubleSpinBox()
        self.cash_input.setRange(0, 10_000_000)
        self.cash_input.setDecimals(2)

        self.upi_input = QDoubleSpinBox()
        self.upi_input.setRange(0, 10_000_000)
        self.upi_input.setDecimals(2)

        self.card_input = QDoubleSpinBox()
        self.card_input.setRange(0, 10_000_000)
        self.card_input.setDecimals(2)

        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)

        form = QFormLayout()
        form.addRow("Shift", self.shift_combo)
        form.addRow("Declared cash", self.cash_input)
        form.addRow("Declared UPI", self.upi_input)
        form.addRow("Declared card", self.card_input)
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
        if self.shift_combo.count() == 0:
            self._show_error("No shifts available.")
            return
        try:
            data = ShiftReconciliationPerform(
                shift_id=self.shift_combo.currentData(),
                declared_cash=Decimal(str(self.cash_input.value())),
                declared_upi=Decimal(str(self.upi_input.value())),
                declared_card=Decimal(str(self.card_input.value())),
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
