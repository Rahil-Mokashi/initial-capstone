"""Generic table-shaped report window (Phase 16): Refresh/Print/Export
PDF/Export Excel around a QTableWidget. Shared by Sales, Payment
Summary, Expense Summary, Credit, and Reconciliation reports so each
doesn't need its own ~150-line window class - only a small factory
function supplying the fetch call and filename stem differs.
"""

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.report_export import build_table_report_html, export_table_csv, export_table_excel, export_table_pdf
from app.ui.print_utils import show_print_preview
from app.ui.qt_utils import describe_unexpected_error


class TableReportWindow(QMainWindow):
    def __init__(
        self,
        actor_user_id: str,
        fetch_report: Callable[..., object],
        filename_stem: str,
        supports_date_filter: bool = False,
    ):
        super().__init__()
        self._actor_user_id = actor_user_id
        self._fetch_report = fetch_report
        self._filename_stem = filename_stem
        self._supports_date_filter = supports_date_filter

        self.setMinimumSize(760, 560)

        self.title_label = QLabel("Report")
        self.title_label.setObjectName("title")

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

        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.setObjectName("secondaryButton")
        self.export_csv_button.setCursor(Qt.PointingHandCursor)
        self.export_csv_button.clicked.connect(self._export_csv)

        self.print_button = QPushButton("Print")
        self.print_button.setObjectName("secondaryButton")
        self.print_button.setCursor(Qt.PointingHandCursor)
        self.print_button.clicked.connect(self._print)

        actions_row = QHBoxLayout()
        if supports_date_filter:
            self.date_from_input = QDateEdit()
            self.date_from_input.setCalendarPopup(True)
            self.date_from_input.setDisplayFormat("yyyy-MM-dd")
            self.date_from_input.setSpecialValueText(" ")
            self.date_from_input.setDate(self.date_from_input.minimumDate())

            self.date_to_input = QDateEdit()
            self.date_to_input.setCalendarPopup(True)
            self.date_to_input.setDisplayFormat("yyyy-MM-dd")
            self.date_to_input.setSpecialValueText(" ")
            self.date_to_input.setDate(self.date_to_input.minimumDate())

            actions_row.addWidget(QLabel("From"))
            actions_row.addWidget(self.date_from_input)
            actions_row.addWidget(QLabel("To"))
            actions_row.addWidget(self.date_to_input)

        actions_row.addWidget(self.refresh_button)
        actions_row.addStretch()
        actions_row.addWidget(self.print_button)
        actions_row.addWidget(self.export_csv_button)
        actions_row.addWidget(self.export_excel_button)
        actions_row.addWidget(self.export_pdf_button)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(self.title_label)
        layout.addLayout(actions_row)
        layout.addWidget(self.error_label)
        layout.addWidget(self.table)

        container = QWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh()

    def _date_filter_args(self) -> dict:
        if not self._supports_date_filter:
            return {}
        args = {}
        if self.date_from_input.date() != self.date_from_input.minimumDate():
            args["date_from"] = self.date_from_input.date().toPython()
        if self.date_to_input.date() != self.date_to_input.minimumDate():
            args["date_to"] = self.date_to_input.date().toPython()
        return args

    def _get_report(self) -> Optional[object]:
        try:
            return self._fetch_report(self._actor_user_id, **self._date_filter_args())
        except Exception as exc:  # noqa: BLE001 - a report window must never crash the app
            self.error_label.setText(describe_unexpected_error(exc))
            self.error_label.show()
            return None

    def refresh(self) -> None:
        self.error_label.hide()
        report = self._get_report()
        if report is None:
            self.table.setRowCount(0)
            return

        self.title_label.setText(report.title)
        self.setWindowTitle(report.title)
        self.table.setColumnCount(len(report.headers))
        self.table.setHorizontalHeaderLabels(report.headers)
        self.table.setRowCount(len(report.rows))
        for row_index, row in enumerate(report.rows):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _export_pdf(self) -> None:
        self._export(export_table_pdf, "PDF Files (*.pdf)", ".pdf")

    def _export_excel(self) -> None:
        self._export(export_table_excel, "Excel Files (*.xlsx)", ".xlsx")

    def _export_csv(self) -> None:
        self._export(export_table_csv, "CSV Files (*.csv)", ".csv")

    def _export(self, export_fn, file_filter: str, default_suffix: str) -> None:
        report = self._get_report()
        if report is None:
            return

        from app.core.paths import default_export_path

        default_name = f"{self._filename_stem}{default_suffix}"
        file_path, _ = QFileDialog.getSaveFileName(self, "Export report", default_export_path(default_name), file_filter)
        if not file_path:
            return

        try:
            export_fn(report, file_path)
        except Exception as exc:  # noqa: BLE001 - last resort so a write failure (disk full, permissions) can't crash the window
            QMessageBox.warning(self, "Could not export", describe_unexpected_error(exc))
            return

        QMessageBox.information(self, "Export complete", f"Report saved to {file_path}")

    def _print(self) -> None:
        report = self._get_report()
        if report is None:
            return
        show_print_preview(build_table_report_html(report), self)
