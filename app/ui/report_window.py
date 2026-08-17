"""Reporting UI (Phase 16). ReportsHubWindow is the single "Reports"
dashboard entry point - it lists every available report (gated per
report on the same permission its own module already uses) rather than
giving each report its own dashboard card, keeping the dashboard from
growing a card per report the way it would if every report were a
top-level module.
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

from app.core.constants import Permission
from app.services.report_export import export_fuel_summary_excel, export_fuel_summary_pdf
from app.ui.print_utils import show_print_preview
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

        from app.core.paths import default_export_path

        default_name = f"fuel_type_summary{default_suffix}"
        file_path, _ = QFileDialog.getSaveFileName(self, "Export report", default_export_path(default_name), file_filter)
        if not file_path:
            return

        try:
            export_fn(summaries, file_path)
        except Exception as exc:  # noqa: BLE001 - last resort so a write failure (disk full, permissions) can't crash the window
            QMessageBox.warning(self, "Could not export", describe_unexpected_error(exc))
            return

        QMessageBox.information(self, "Export complete", f"Report saved to {file_path}")

    def _print(self) -> None:
        try:
            summaries = self._report_service.get_fuel_type_summary(self._actor_user_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not print", describe_unexpected_error(exc))
            return

        show_print_preview(_build_report_html(summaries), self)


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


class ReportsHubWindow(QMainWindow):
    """Landing screen for the Reports module: a list of every report the
    acting user can open, gated per-report on that report's own
    permission."""

    def __init__(self, report_service, auth_service, actor_user_id: str, analytics_service):
        super().__init__()
        self._report_service = report_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id
        self._analytics_service = analytics_service
        self._open_windows = []

        self.setWindowTitle("Reports")
        self.setMinimumSize(420, 480)

        title = QLabel("Reports")
        title.setObjectName("title")

        subtitle = QLabel("Choose a report to view, print, or export.")
        subtitle.setObjectName("subtitle")

        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)

        report_definitions = [
            ("Fuel Type Summary", Permission.INVENTORY_VIEW, self._open_fuel_summary),
            ("Sales Report", Permission.SALE_VIEW, lambda: self._open_table_report(
                self._report_service.get_sales_report, "sales_report", supports_date_filter=True)),
            ("Payment Summary Report", Permission.SALE_VIEW, lambda: self._open_table_report(
                self._report_service.get_payment_summary_report, "payment_summary_report", supports_date_filter=True)),
            ("Expense Summary Report", Permission.EXPENSE_VIEW, lambda: self._open_table_report(
                self._report_service.get_expense_summary_report, "expense_summary_report", supports_date_filter=True)),
            ("Credit Report by Fuel Type", Permission.CREDIT_VIEW, lambda: self._open_table_report(
                self._report_service.get_credit_fuel_type_report, "credit_fuel_type_report")),
            ("Customer Outstanding Report", Permission.CREDIT_VIEW, lambda: self._open_table_report(
                self._report_service.get_customer_outstanding_report, "customer_outstanding_report")),
            ("Shift Reconciliation Report", Permission.RECONCILIATION_VIEW, lambda: self._open_table_report(
                self._report_service.get_reconciliation_report, "reconciliation_report", supports_date_filter=True)),
            # problemstatement.md #25-32: the daily/attendant/inventory/
            # financial/HR reports. Listed after the per-module reports
            # above because these cut across modules rather than
            # belonging to one.
            ("Daily Summary Report", Permission.SALE_VIEW, lambda: self._open_table_report(
                self._report_service.get_daily_summary_report, "daily_summary_report", supports_date_filter=True)),
            ("Attendant & Nozzle Report", Permission.SALE_VIEW, lambda: self._open_table_report(
                self._report_service.get_attendant_nozzle_report, "attendant_nozzle_report",
                supports_date_filter=True, filter_by=("employee", "nozzle"))),
            ("Fuel Movement Report", Permission.INVENTORY_VIEW, lambda: self._open_table_report(
                self._report_service.get_fuel_movement_report, "fuel_movement_report", supports_date_filter=True)),
            ("Cash Book", Permission.EXPENSE_VIEW, lambda: self._open_table_report(
                self._report_service.get_cash_book_report, "cash_book", supports_date_filter=True)),
            ("Attendance Report", Permission.ATTENDANCE_VIEW, lambda: self._open_table_report(
                self._report_service.get_attendance_report, "attendance_report",
                supports_date_filter=True, filter_by=("employee",))),
            ("Business Insights (Performance & Forecast)", Permission.ANALYTICS_VIEW, self._open_analytics),
        ]

        any_visible = False
        for label, permission, handler in report_definitions:
            if not self._auth_service.check_permission(actor_user_id, permission.value):
                continue
            any_visible = True
            button = QPushButton(label)
            button.setObjectName("secondaryButton")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(handler)
            buttons_layout.addWidget(button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        if not any_visible:
            empty = QLabel("No reports available for your role yet.")
            empty.setObjectName("subtitle")
            layout.addWidget(empty)
        layout.addLayout(buttons_layout)
        layout.addStretch()

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

    def _open_fuel_summary(self) -> None:
        window = FuelTypeSummaryReportWindow(self._report_service, self._auth_service, self._actor_user_id)
        self._open_windows.append(window)
        window.show()

    def _open_table_report(
        self,
        fetch_report,
        filename_stem: str,
        supports_date_filter: bool = False,
        filter_by: tuple = (),
    ) -> None:
        """filter_by names the extra dimensions this report accepts
        ("employee", "nozzle"). The choices themselves come from
        ReportService, which gates each list on the permission that owns
        that data - so a user who may open the report but not see the
        staff roster simply gets no employee drop-down."""
        from app.ui.table_report_window import TableReportWindow

        choice_filters = []
        if filter_by:
            try:
                options = self._report_service.get_report_filter_options(self._actor_user_id)
            except Exception:  # noqa: BLE001 - a filter list must never stop a report opening
                options = {}
            if "employee" in filter_by:
                choice_filters.append(("Employee", "employee_id", options.get("employees", [])))
            if "nozzle" in filter_by:
                choice_filters.append(("Nozzle", "nozzle_id", options.get("nozzles", [])))

        window = TableReportWindow(
            self._actor_user_id, fetch_report, filename_stem, supports_date_filter, choice_filters
        )
        self._open_windows.append(window)
        window.show()

    def _open_analytics(self) -> None:
        from app.ui.analytics_window import AnalyticsWindow

        window = AnalyticsWindow(self._analytics_service, self._actor_user_id)
        self._open_windows.append(window)
        window.show()
