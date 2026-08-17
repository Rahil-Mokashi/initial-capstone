"""Fuel prices screen.

Until this existed there was no way anywhere in the application to set a
fuel's selling price: seed.py created Petrol, Diesel and Power at 0.00
and nothing could change them, so every sale on a fresh install booked
zero revenue. See app/services/fuel_service.py for the full account.

The screen is deliberately small - a table of fuels with their current
price, a change-price dialog that demands a reason, and a per-fuel price
history - because that is the whole job. What it does do carefully is
make an unpriced fuel visually obvious, since a price of zero is not an
empty state, it is a trap.
"""

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import Permission
from app.core.exceptions import AppError
from app.schemas.fuel import MAX_REASONABLE_RATE_PER_LITER, FuelRateChange
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error


class FuelPriceWindow(QMainWindow):
    def __init__(self, actor_user_id: str, fuel_service, auth_service):
        super().__init__()
        self._actor_user_id = actor_user_id
        self._fuel_service = fuel_service
        self._auth_service = auth_service
        self._can_manage = auth_service.check_permission(
            actor_user_id, Permission.FUEL_PRICE_MANAGE.value
        )

        self.setWindowTitle("Fuel Prices")
        self.setMinimumSize(760, 520)

        title = QLabel("Fuel Prices")
        title.setObjectName("title")

        subtitle = QLabel(
            "The rate each fuel currently sells at. A sale snapshots the rate at the "
            "moment it is recorded, so changing a price here never alters a past sale."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)

        self.change_price_button = QPushButton("Change Price")
        self.change_price_button.setCursor(Qt.PointingHandCursor)
        self.change_price_button.clicked.connect(self._change_price)
        self.change_price_button.setEnabled(self._can_manage)
        if not self._can_manage:
            self.change_price_button.setToolTip("Only a manager can change a fuel price.")

        self.history_button = QPushButton("Price History")
        self.history_button.setObjectName("secondaryButton")
        self.history_button.setCursor(Qt.PointingHandCursor)
        self.history_button.clicked.connect(self._show_history)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Fuel", "Rate per litre", "Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._change_price)

        actions = QHBoxLayout()
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        actions.addWidget(self.history_button)
        actions.addWidget(self.change_price_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.error_label)
        layout.addLayout(actions)
        layout.addWidget(self.table, stretch=1)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh()

    # ------------------------------------------------------------------

    def refresh(self) -> None:
        self.error_label.hide()
        try:
            fuels = self._fuel_service.list_fuels(self._actor_user_id)
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self._fuels = fuels
        self.table.setRowCount(0)
        unpriced = 0
        for row, fuel in enumerate(fuels):
            rate = Decimal(str(fuel.rate_per_liter or 0))
            priced = rate > 0
            if not priced:
                unpriced += 1

            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(fuel.fuel_type))

            rate_item = QTableWidgetItem(f"₹{rate:,.2f}" if priced else "—")
            rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, rate_item)

            status_item = QTableWidgetItem("Priced" if priced else "No price set")
            if not priced:
                # A zero price is not an empty state, it is a fuel that
                # cannot be sold - make that unmissable.
                status_item.setForeground(QColor("#B91C1C"))
            self.table.setItem(row, 2, status_item)

        if unpriced:
            self.warning_label.setText(
                f"{unpriced} fuel type(s) have no selling price set and cannot be sold. "
                "Set a price before the next shift opens."
            )
            self.warning_label.show()
        else:
            self.warning_label.hide()

    def _selected_fuel(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._fuels):
            self._show_error("Select a fuel first.")
            return None
        return self._fuels[row]

    def _change_price(self) -> None:
        if not self._can_manage:
            return
        fuel = self._selected_fuel()
        if fuel is None:
            return
        dialog = FuelRateDialog(fuel, self._actor_user_id, self._fuel_service, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _show_history(self) -> None:
        fuel = self._selected_fuel()
        if fuel is None:
            return
        try:
            history = self._fuel_service.get_price_history(self._actor_user_id, fuel.id)
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return
        FuelPriceHistoryDialog(fuel, history, self).exec()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


class FuelRateDialog(QDialog):
    """Change one fuel's price. A reason is mandatory - the same rule
    every other consequential change in this app follows."""

    def __init__(self, fuel, actor_user_id: str, fuel_service, parent=None):
        super().__init__(parent)
        self._fuel = fuel
        self._actor_user_id = actor_user_id
        self._fuel_service = fuel_service

        self.setWindowTitle(f"Change price — {fuel.fuel_type}")
        self.setMinimumWidth(420)

        current = Decimal(str(fuel.rate_per_liter or 0))
        current_label = QLabel(
            f"Current rate: ₹{current:,.2f}" if current > 0 else "Current rate: not set"
        )
        current_label.setObjectName("subtitle")

        self.rate_input = QDoubleSpinBox()
        self.rate_input.setDecimals(2)
        self.rate_input.setMinimum(0.01)
        self.rate_input.setMaximum(float(MAX_REASONABLE_RATE_PER_LITER))
        self.rate_input.setSingleStep(0.10)
        self.rate_input.setPrefix("₹ ")
        self.rate_input.setValue(float(current) if current > 0 else 100.00)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("e.g. Daily OMC revision, 17 Aug")
        self.reason_input.setMaxLength(500)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        form = QFormLayout()
        form.addRow("New rate per litre", self.rate_input)
        form.addRow("Reason", self.reason_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        chain_enter_to_next_field(self.rate_input, self.reason_input)
        self.reason_input.returnPressed.connect(self._save)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(current_label)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        try:
            self._fuel_service.set_rate(
                self._actor_user_id,
                self._fuel.id,
                FuelRateChange(
                    new_rate_per_liter=Decimal(str(self.rate_input.value())),
                    reason=self.reason_input.text().strip(),
                ),
            )
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


class FuelPriceHistoryDialog(QDialog):
    """Every change ever made to this fuel's price, newest first."""

    def __init__(self, fuel, history, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Price history — {fuel.fuel_type}")
        self.setMinimumSize(640, 420)

        table = QTableWidget(len(history), 4)
        table.setHorizontalHeaderLabels(["Effective from", "From", "To", "Reason"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)

        for row, entry in enumerate(history):
            effective = entry.effective_from
            table.setItem(row, 0, QTableWidgetItem(
                effective.strftime("%Y-%m-%d %H:%M") if effective else ""))
            old_rate = entry.old_rate_per_liter
            table.setItem(row, 1, QTableWidgetItem(
                f"₹{Decimal(str(old_rate)):,.2f}" if old_rate is not None else "—"))
            table.setItem(row, 2, QTableWidgetItem(
                f"₹{Decimal(str(entry.new_rate_per_liter)):,.2f}"))
            table.setItem(row, 3, QTableWidgetItem(entry.reason or ""))

        empty = QLabel("No price changes recorded yet.")
        empty.setObjectName("subtitle")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        if history:
            layout.addWidget(table, stretch=1)
        else:
            layout.addWidget(empty)
        layout.addWidget(buttons)
        self.setLayout(layout)
