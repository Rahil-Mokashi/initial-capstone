"""Reporting UI (Phase 16, first slice). Shows an inventory summary
sectioned by fuel type, per the user's explicit request. Pure
presentation — the aggregation lives in ReportService.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.qt_utils import describe_unexpected_error


class FuelTypeSummaryCard(QWidget):
    """One fuel type's section of the report."""

    def __init__(self, summary, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        title = QLabel(summary.fuel_type)
        title.setObjectName("sectionTitle")

        rows = [
            f"Tanks: {summary.tank_count}",
            f"Total capacity: {summary.total_capacity:g} L",
            f"Total current stock: {summary.total_current_stock:g} L",
            f"Nozzles: {summary.active_nozzle_count} active / {summary.nozzle_count} total",
        ]
        if summary.latest_variance_classification is not None:
            rows.append(
                f"Latest reconciliation variance: {summary.latest_variance_percent:+.2f}% "
                f"({summary.latest_variance_classification.replace('_', ' ').title()})"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)
        layout.addWidget(title)
        for row in rows:
            layout.addWidget(QLabel(row))
        self.setLayout(layout)


class FuelTypeSummaryReportWindow(QMainWindow):
    """problemstatement.md #30/#31: fuel-type-sectioned inventory summary.

    Full Phase 16 scope (print/PDF/Excel export, print preview, the rest
    of the daily/shift/HR/financial/management reports) is not attempted
    here — this is a first, on-screen slice covering what the current
    modules (Tank, Nozzle) can already report on.
    """

    def __init__(self, report_service, auth_service, actor_user_id: str):
        super().__init__()
        self._report_service = report_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Fuel Type Summary")
        self.setMinimumSize(520, 560)

        title = QLabel("Fuel Type Summary")
        title.setObjectName("title")

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)

        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(16)

        cards_container = QWidget()
        cards_container.setLayout(self.cards_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(cards_container)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(self.refresh_button)
        layout.addWidget(scroll)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh()

    def refresh(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        try:
            summaries = self._report_service.get_fuel_type_summary(self._actor_user_id)
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the window
            error_label = QLabel(describe_unexpected_error(exc))
            error_label.setObjectName("errorLabel")
            self.cards_layout.addWidget(error_label)
            return

        if not summaries:
            empty = QLabel("No fuel types configured yet.")
            empty.setObjectName("subtitle")
            self.cards_layout.addWidget(empty)
            return

        for summary in summaries:
            self.cards_layout.addWidget(FuelTypeSummaryCard(summary))
        self.cards_layout.addStretch()
