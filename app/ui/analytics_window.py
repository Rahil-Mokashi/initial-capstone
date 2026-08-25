"""Business Insights UI: period performance (daily/weekly/monthly/
quarterly/yearly profitability per fuel type) and a sales forecast
(trend-based prediction of next week's sales per fuel type).

Both tabs convert their domain dataclasses (PeriodPerformanceReport,
FuelSalesForecast) into the same TableReport shape used everywhere
else in the app, reusing the generic Print/PDF/Excel/CSV export
functions rather than writing new export code for this feature.
"""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.dates import PeriodType
from app.services.report_export import export_table_csv, export_table_excel, export_table_pdf
from app.services.report_service import TableReport
from app.ui.print_utils import show_print_preview
from app.ui.qt_utils import describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget

PERIOD_LABELS = [
    ("Daily", PeriodType.DAY),
    ("Weekly", PeriodType.WEEK),
    ("Monthly", PeriodType.MONTH),
    ("Quarterly", PeriodType.QUARTER),
    ("Yearly", PeriodType.YEAR),
]

TREND_LABELS = {
    "increasing": "▲ Likely hike",
    "decreasing": "▼ Possible dip",
    "stable": "▬ Stable",
    "insufficient_data": "Not enough data",
}


def _performance_to_table_report(report) -> TableReport:
    headers = ["Fuel Type", "Revenue", "Quantity (L)", "Avg. Cost", "Est. Cost of Goods", "Est. Gross Profit", "Margin %"]
    rows = []
    for row in report.fuel_breakdown:
        rows.append(
            [
                row.fuel_type,
                f"{row.revenue:.2f}",
                f"{row.quantity_sold:.2f}",
                f"{row.weighted_avg_cost:.2f}" if row.weighted_avg_cost is not None else "N/A",
                f"{row.estimated_cost_of_goods:.2f}" if row.estimated_cost_of_goods is not None else "N/A",
                f"{row.estimated_gross_profit:.2f}" if row.estimated_gross_profit is not None else "N/A",
                f"{row.gross_margin_percent:.1f}" if row.gross_margin_percent is not None else "N/A",
            ]
        )
    rows.append(["", "", "", "", "", "", ""])
    rows.append(["Total Revenue", f"{report.total_revenue:.2f}", "", "", "", "", ""])
    rows.append(["Total Est. Gross Profit", f"{report.total_estimated_gross_profit:.2f}" if report.total_estimated_gross_profit is not None else "N/A", "", "", "", "", ""])
    rows.append(["Total Approved Expenses", f"{report.total_expenses:.2f}", "", "", "", "", ""])
    rows.append(["Est. Net Profit", f"{report.estimated_net_profit:.2f}" if report.estimated_net_profit is not None else "N/A", "", "", "", "", ""])

    title = f"Business Performance - {report.period_type.title()} ({report.period_start} to {report.period_end})"
    return TableReport(title=title, headers=headers, rows=rows)


def _forecasts_to_table_report(forecasts) -> TableReport:
    headers = ["Fuel Type", "Trend", "Predicted Next Week (L)", "Predicted Revenue", "Change vs Last Week"]
    rows = []
    for forecast in forecasts:
        rows.append(
            [
                forecast.fuel_type,
                TREND_LABELS.get(forecast.trend, forecast.trend),
                f"{forecast.predicted_next_week_quantity:.2f}" if forecast.predicted_next_week_quantity is not None else "N/A",
                f"{forecast.predicted_next_week_revenue:.2f}" if forecast.predicted_next_week_revenue is not None else "N/A",
                f"{forecast.trend_percent:+.1f}%" if forecast.trend_percent is not None else "N/A",
            ]
        )
    return TableReport(title="Sales Forecast", headers=headers, rows=rows)


class AnalyticsWindow(QWidget):
    def __init__(self, analytics_service, actor_user_id: str):
        super().__init__()
        self.setWindowTitle("Business Insights")
        self.setMinimumSize(880, 620)

        title = QLabel("Business Insights")
        title.setObjectName("title")

        self.performance_tab = PerformanceTab(analytics_service, actor_user_id)
        self.forecast_tab = ForecastTab(analytics_service, actor_user_id)

        tabs = QTabWidget()
        tabs.addTab(self.performance_tab, "Performance")
        tabs.addTab(self.forecast_tab, "Sales Forecast")

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(tabs)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)


class PerformanceTab(QWidget):
    def __init__(self, analytics_service, actor_user_id: str):
        super().__init__()
        self._analytics_service = analytics_service
        self._actor_user_id = actor_user_id
        self._report = None

        self.period_combo = QComboBox()
        for label, _ in PERIOD_LABELS:
            self.period_combo.addItem(label)

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        self.date_input.setDate(date.today())

        self.generate_button = QPushButton("Generate")
        self.generate_button.setCursor(Qt.PointingHandCursor)
        self.generate_button.clicked.connect(self._generate)

        self.print_button = QPushButton("Print")
        self.print_button.setObjectName("secondaryButton")
        self.print_button.clicked.connect(self._print)

        self.export_pdf_button = QPushButton("Export PDF")
        self.export_pdf_button.setObjectName("secondaryButton")
        self.export_pdf_button.clicked.connect(lambda: self._export(export_table_pdf, "PDF Files (*.pdf)", ".pdf"))

        self.export_excel_button = QPushButton("Export Excel")
        self.export_excel_button.setObjectName("secondaryButton")
        self.export_excel_button.clicked.connect(lambda: self._export(export_table_excel, "Excel Files (*.xlsx)", ".xlsx"))

        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.setObjectName("secondaryButton")
        self.export_csv_button.clicked.connect(lambda: self._export(export_table_csv, "CSV Files (*.csv)", ".csv"))

        controls_row = QHBoxLayout()
        controls_row.addWidget(QLabel("Period"))
        controls_row.addWidget(self.period_combo)
        controls_row.addWidget(QLabel("As of"))
        controls_row.addWidget(self.date_input)
        controls_row.addWidget(self.generate_button)
        controls_row.addStretch()
        controls_row.addWidget(self.print_button)
        controls_row.addWidget(self.export_csv_button)
        controls_row.addWidget(self.export_excel_button)
        controls_row.addWidget(self.export_pdf_button)

        self.note_label = QLabel(
            "Profit figures use the weighted-average purchase cost for each fuel type as of the period end - "
            "\"N/A\" means no purchase history exists yet for that fuel."
        )
        self.note_label.setObjectName("subtitle")
        self.note_label.setWordWrap(True)

        self.table = QTableWidget(0, 0)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(controls_row)
        layout.addWidget(self.note_label)
        layout.addWidget(self.error_label)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self._generate()

    def _selected_period_type(self) -> PeriodType:
        return PERIOD_LABELS[self.period_combo.currentIndex()][1]

    def _generate(self) -> None:
        self.error_label.hide()
        try:
            performance = self._analytics_service.get_period_performance(
                self._actor_user_id, self._selected_period_type(), self.date_input.date().toPython()
            )
        except Exception as exc:  # noqa: BLE001 - a report tab must never crash the app
            self.error_label.setText(describe_unexpected_error(exc))
            self.error_label.show()
            self._report = None
            self.table.setRowCount(0)
            return

        self._report = _performance_to_table_report(performance)
        self.table.setColumnCount(len(self._report.headers))
        self.table.setHorizontalHeaderLabels(self._report.headers)
        self.table.setRowCount(len(self._report.rows))
        for row_index, row in enumerate(self._report.rows):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _print(self) -> None:
        if self._report is None:
            return
        from app.services.report_export import build_table_report_html

        show_print_preview(build_table_report_html(self._report), self)

    def _export(self, export_fn, file_filter: str, default_suffix: str) -> None:
        if self._report is None:
            return
        from app.core.paths import default_export_path

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export report", default_export_path(f"business_performance{default_suffix}"), file_filter
        )
        if not file_path:
            return
        try:
            export_fn(self._report, file_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not export", describe_unexpected_error(exc))
            return
        QMessageBox.information(self, "Export complete", f"Report saved to {file_path}")


class ForecastTab(QWidget):
    def __init__(self, analytics_service, actor_user_id: str):
        super().__init__()
        self._analytics_service = analytics_service
        self._actor_user_id = actor_user_id
        self._forecasts = []
        self._report = None

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)

        self.print_button = QPushButton("Print")
        self.print_button.setObjectName("secondaryButton")
        self.print_button.clicked.connect(self._print)

        self.export_pdf_button = QPushButton("Export PDF")
        self.export_pdf_button.setObjectName("secondaryButton")
        self.export_pdf_button.clicked.connect(lambda: self._export(export_table_pdf, "PDF Files (*.pdf)", ".pdf"))

        top_row = QHBoxLayout()
        top_row.addWidget(self.refresh_button)
        top_row.addStretch()
        top_row.addWidget(self.print_button)
        top_row.addWidget(self.export_pdf_button)

        self.table = QTableWidget(0, 0)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.explanations_label = QLabel("")
        self.explanations_label.setObjectName("subtitle")
        self.explanations_label.setWordWrap(True)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(self.error_label)
        layout.addWidget(self.table)
        layout.addWidget(self.explanations_label)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        self.error_label.hide()
        try:
            self._forecasts = self._analytics_service.get_sales_forecast(self._actor_user_id)
        except Exception as exc:  # noqa: BLE001
            self.error_label.setText(describe_unexpected_error(exc))
            self.error_label.show()
            self._forecasts = []
            self._report = None
            self.table.setRowCount(0)
            self.explanations_label.setText("")
            return

        self._report = _forecasts_to_table_report(self._forecasts)
        self.table.setColumnCount(len(self._report.headers))
        self.table.setHorizontalHeaderLabels(self._report.headers)
        self.table.setRowCount(len(self._report.rows))
        for row_index, row in enumerate(self._report.rows):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        self.explanations_label.setText("\n\n".join(f.explanation for f in self._forecasts))

    def _print(self) -> None:
        if self._report is None:
            return
        from app.services.report_export import build_table_report_html

        html = build_table_report_html(self._report)
        html += "<p>" + "</p><p>".join(f.explanation for f in self._forecasts) + "</p>"
        show_print_preview(html, self)

    def _export(self, export_fn, file_filter: str, default_suffix: str) -> None:
        if self._report is None:
            return
        from app.core.paths import default_export_path

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export forecast", default_export_path(f"sales_forecast{default_suffix}"), file_filter
        )
        if not file_path:
            return
        try:
            export_fn(self._report, file_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not export", describe_unexpected_error(exc))
            return
        QMessageBox.information(self, "Export complete", f"Forecast saved to {file_path}")
