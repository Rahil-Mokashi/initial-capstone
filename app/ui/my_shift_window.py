"""Attendant self-service view (problemstatement.md #38: "An attendant
should see: My Shift, My Nozzle, Opening Meter..."). Pure presentation —
the lookup itself lives in ShiftService.get_my_active_assignment.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from app.ui.qt_utils import describe_unexpected_error


class MyShiftWindow(QMainWindow):
    """Shows the logged-in attendant's current nozzle/fuel assignment, if any."""

    def __init__(self, shift_service, auth_service, actor_user_id: str):
        super().__init__()
        self._shift_service = shift_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("My Shift")
        self.setMinimumSize(480, 360)

        title = QLabel("My Shift")
        title.setObjectName("title")

        self.body_layout = QVBoxLayout()
        self.body_layout.setSpacing(4)

        layout = QVBoxLayout()
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)
        layout.addWidget(title)
        layout.addLayout(self.body_layout)
        layout.addStretch()

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh()

    def refresh(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        try:
            assignment = self._shift_service.get_my_active_assignment(self._actor_user_id)
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the window
            self._add_row(describe_unexpected_error(exc), object_name="errorLabel")
            return

        if not assignment:
            empty = QLabel("You're not currently assigned to a nozzle. Check with your shift supervisor.")
            empty.setObjectName("subtitle")
            empty.setWordWrap(True)
            self.body_layout.addWidget(empty)
            return

        shift = assignment.shift
        nozzle = assignment.nozzle

        card = QWidget()
        card.setObjectName("card")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(10)

        card_layout.addWidget(self._field_label(f"{shift.shift_label} shift — {shift.shift_date.isoformat()}", "sectionTitle"))
        card_layout.addWidget(self._field_label(f"Nozzle: {nozzle.code if nozzle else '—'}"))
        card_layout.addWidget(self._field_label(f"Fuel type: {nozzle.fuel.fuel_type if nozzle and nozzle.fuel else '—'}"))
        card_layout.addWidget(self._field_label(f"Dispenser: {nozzle.dispenser.code if nozzle and nozzle.dispenser else '—'}"))
        card_layout.addWidget(self._field_label(f"Opening meter: {assignment.opening_meter:g}"))
        card_layout.addWidget(self._field_label(f"Status: {assignment.status.title()}"))
        card.setLayout(card_layout)

        self.body_layout.addWidget(card)

    def _field_label(self, text: str, object_name: str = "") -> QLabel:
        label = QLabel(text)
        if object_name:
            label.setObjectName(object_name)
        return label

    def _add_row(self, text: str, object_name: str = "") -> None:
        self.body_layout.addWidget(self._field_label(text, object_name))
