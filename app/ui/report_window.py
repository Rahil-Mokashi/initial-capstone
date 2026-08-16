"""Reporting UI (Phase 16, first slice). Shows an inventory summary
sectioned by fuel type, per the user's explicit request. Pure
presentation — the aggregation lives in ReportService.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.report_export import export_fuel_summary_excel, export_fuel_summary_pdf
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

        self.export_pdf_button = QPushButton("Export PDF")
        self.export_pdf_button.setObjectName("secondaryButton")
        self.export_pdf_button.setCursor(Qt.PointingHandCursor)
        self.export_pdf_button.clicked.connect(self._export_pdf)

        self.export_excel_button = QPushButton("Export Excel")
        self.export_excel_button.setObjectName("secondaryButton")
        self.export_excel_button.setCursor(Qt.PointingHandCursor)
        self.export_excel_button.clicked.connect(self._export_excel)

        self.print_button = QPushButton("Print")
        self.print_button.setObjectName("secondaryButton")
        self.print_button.setCursor(Qt.PointingHandCursor)
        self.print_button.clicked.connect(self._print)

        actions_row = QHBoxLayout()
        actions_row.addWidget(self.refresh_button)
        actions_row.addStretch()
        actions_row.addWidget(self.print_button)
        actions_row.addWidget(self.export_excel_button)
        actions_row.addWidget(self.export_pdf_button)

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
        layout.addLayout(actions_row)
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

    def _export_pdf(self) -> None:
        self._export(export_fuel_summary_pdf, "PDF Files (*.pdf)", ".pdf")

    def _export_excel(self) -> None:
        self._export(export_fuel_summary_excel, "Excel Files (*.xlsx)", ".xlsx")

    def _export(self, export_fn, file_filter: str, default_suffix: str) -> None:
        try:
            summaries = self._report_service.get_fuel_type_summary(self._actor_user_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not export", describe_unexpected_error(exc))
            return

        default_name = f"fuel_type_summary{default_suffix}"
        file_path, _ = QFileDialog.getSaveFileName(self, "Export report", default_name, file_filter)
        if not file_path:
            return

        try:
            export_fn(summaries, file_path)
        except Exception as exc:  # noqa: BLE001 - last resort so a write failure (disk full, permissions) can't crash the window
            QMessageBox.warning(self, "Could not export", describe_unexpected_error(exc))
            return

        QMessageBox.information(self, "Export complete", f"Report saved to {file_path}")

    def _print(self) -> None:
        from PySide6.QtGui import QTextDocument
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        try:
            summaries = self._report_service.get_fuel_type_summary(self._actor_user_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not print", describe_unexpected_error(exc))
            return

        document = QTextDocument()
        document.setHtml(_build_report_html(summaries))

        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.Accepted:
            document.print_(printer)


def _build_report_html(summaries) -> str:
    from datetime import datetime

    rows = []
    for summary in summaries:
        variance = (
            f"{summary.latest_variance_percent:+.2f}%" if summary.latest_variance_percent is not None else "—"
        )
        classification = (summary.latest_variance_classification or "—").replace("_", " ").title()
        rows.append(
            "<tr>"
            f"<td>{summary.fuel_type}</td><td>{summary.tank_count}</td>"
            f"<td>{summary.total_capacity:.2f}</td><td>{summary.total_current_stock:.2f}</td>"
            f"<td>{summary.active_nozzle_count}/{summary.nozzle_count}</td>"
            f"<td>{variance}</td><td>{classification}</td>"
            "</tr>"
        )

    return f"""
    <h2>Fuel Type Summary</h2>
    <p>Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    <table border="1" cellspacing="0" cellpadding="6" width="100%">
    <tr>
        <th>Fuel Type</th><th>Tanks</th><th>Capacity (L)</th><th>Stock (L)</th>
        <th>Nozzles</th><th>Variance %</th><th>Classification</th>
    </tr>
    {''.join(rows)}
    </table>
    """
