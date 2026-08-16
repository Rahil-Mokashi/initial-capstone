"""Nozzle/Dispenser master-data UI (Phase 8). Two tabs: Dispensers and
Nozzles. Pure presentation — validation and business rules live in
NozzleService and its Pydantic schemas.
"""

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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

from app.core.constants import NozzleStatus, Permission
from app.core.exceptions import AppError
from app.database.base import StatusEnum
from app.schemas.nozzle import DispenserCreate, NozzleCreate
from app.ui.qt_utils import describe_unexpected_error

DISPENSER_HEADERS = ["Code", "Status"]
NOZZLE_HEADERS = ["Code", "Dispenser", "Fuel Type", "Status"]


class NozzleManagementWindow(QMainWindow):
    """Tabbed Dispensers/Nozzles master-data screen."""

    def __init__(self, nozzle_service, fuel_service_repo, auth_service, actor_user_id: str):
        super().__init__()
        self._nozzle_service = nozzle_service
        self._fuel_repo = fuel_service_repo
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id
        self._can_manage = auth_service.check_permission(actor_user_id, Permission.NOZZLE_MANAGE.value)

        self.setWindowTitle("Nozzle Management")
        self.setMinimumSize(760, 520)

        title = QLabel("Nozzle Management")
        title.setObjectName("title")

        self.dispenser_tab = DispenserTab(nozzle_service, actor_user_id, self._can_manage)
        self.nozzle_tab = NozzleTab(nozzle_service, fuel_service_repo, actor_user_id, self._can_manage)

        tabs = QTabWidget()
        tabs.addTab(self.dispenser_tab, "Dispensers")
        tabs.addTab(self.nozzle_tab, "Nozzles")
        tabs.currentChanged.connect(lambda _: self.nozzle_tab.refresh())

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(tabs)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)


class DispenserTab(QWidget):
    def __init__(self, nozzle_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._nozzle_service = nozzle_service
        self._actor_user_id = actor_user_id
        self._can_manage = can_manage

        self.add_button = QPushButton("+ Add Dispenser")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(DISPENSER_HEADERS))
        self.table.setHorizontalHeaderLabels(DISPENSER_HEADERS)
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
        dispensers = self._nozzle_service.list_dispensers(self._actor_user_id)
        self.table.setRowCount(len(dispensers))
        for row_index, dispenser in enumerate(dispensers):
            self.table.setItem(row_index, 0, QTableWidgetItem(dispenser.code))
            self.table.setItem(row_index, 1, QTableWidgetItem(dispenser.status.title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, dispenser.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = DispenserFormDialog(self._nozzle_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _toggle_selected_status(self) -> None:
        if not self._can_manage:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        dispenser_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        current_status = self.table.item(rows[0].row(), 1).text().lower()
        new_status = StatusEnum.INACTIVE if current_status == "active" else StatusEnum.ACTIVE

        reason, ok = QInputDialog.getText(self, "Change status", f"Reason to mark {new_status.value}:")
        if not ok or not reason.strip():
            return
        try:
            self._nozzle_service.set_dispenser_status(self._actor_user_id, dispenser_id, new_status, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not change status", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change status", describe_unexpected_error(exc))
        self.refresh()


class DispenserFormDialog(QDialog):
    def __init__(self, nozzle_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._nozzle_service = nozzle_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Add Dispenser")
        self.setMinimumWidth(320)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g. D1")
        self.code_input.returnPressed.connect(self._save)

        form = QFormLayout()
        form.addRow("Code", self.code_input)

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
            self._nozzle_service.create_dispenser(self._actor_user_id, DispenserCreate(code=self.code_input.text()))
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


class NozzleTab(QWidget):
    def __init__(self, nozzle_service, fuel_repo, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._nozzle_service = nozzle_service
        self._fuel_repo = fuel_repo
        self._actor_user_id = actor_user_id
        self._can_manage = can_manage

        self.add_button = QPushButton("+ Add Nozzle")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(NOZZLE_HEADERS))
        self.table.setHorizontalHeaderLabels(NOZZLE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._change_selected_status)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        nozzles = self._nozzle_service.list_nozzles(self._actor_user_id)
        self.table.setRowCount(len(nozzles))
        for row_index, nozzle in enumerate(nozzles):
            self.table.setItem(row_index, 0, QTableWidgetItem(nozzle.code))
            self.table.setItem(row_index, 1, QTableWidgetItem(nozzle.dispenser.code if nozzle.dispenser else ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(nozzle.fuel.fuel_type if nozzle.fuel else ""))
            self.table.setItem(row_index, 3, QTableWidgetItem(nozzle.status.replace("_", " ").title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, nozzle.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = NozzleFormDialog(self._nozzle_service, self._fuel_repo, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _change_selected_status(self) -> None:
        if not self._can_manage:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        nozzle_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)

        status_names = [s.value for s in NozzleStatus]
        new_status_name, ok = QInputDialog.getItem(self, "Change status", "New status:", status_names, editable=False)
        if not ok:
            return

        reason, ok = QInputDialog.getText(self, "Change status", "Reason:")
        if not ok or not reason.strip():
            return

        try:
            self._nozzle_service.set_nozzle_status(
                self._actor_user_id, nozzle_id, NozzleStatus(new_status_name), reason.strip()
            )
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not change status", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change status", describe_unexpected_error(exc))
        self.refresh()


class NozzleFormDialog(QDialog):
    def __init__(self, nozzle_service, fuel_repo, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._nozzle_service = nozzle_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Add Nozzle")
        self.setMinimumWidth(360)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g. N1")
        self.code_input.returnPressed.connect(self._save)

        self.dispenser_combo = QComboBox()
        for dispenser in nozzle_service.list_dispensers(actor_user_id):
            if dispenser.status == "active":
                self.dispenser_combo.addItem(dispenser.code, dispenser.id)

        self.fuel_combo = QComboBox()
        for fuel in fuel_repo.list_active():
            self.fuel_combo.addItem(fuel.fuel_type, fuel.id)

        form = QFormLayout()
        form.addRow("Code", self.code_input)
        form.addRow("Dispenser", self.dispenser_combo)
        form.addRow("Fuel type", self.fuel_combo)

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
        if self.dispenser_combo.count() == 0:
            self._show_error("No active dispensers available. Add one first.")
            return
        if self.fuel_combo.count() == 0:
            self._show_error("No fuel types available.")
            return
        try:
            data = NozzleCreate(
                code=self.code_input.text(),
                dispenser_id=self.dispenser_combo.currentData(),
                fuel_id=self.fuel_combo.currentData(),
            )
            self._nozzle_service.create_nozzle(self._actor_user_id, data)
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
