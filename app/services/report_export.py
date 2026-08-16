"""PDF/Excel export for reports (CLAUDE.md Reporting Rules: every
important report must support Print, Print Preview, PDF export, and
Excel export). Pure formatting functions - the caller fetches data
through a permission-checked service method first; nothing here
touches the database or checks permissions.
"""

from datetime import datetime
from typing import List, Sequence

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.report_service import FuelTypeSummary, TableReport


def export_table_pdf(report: TableReport, file_path: str) -> None:
    """Generic PDF export shared by every table-shaped report (Sales,
    Payments, Expenses, Credit, Reconciliation, ...) so each new report
    doesn't need its own copy of this layout code."""

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(report.title, styles["Title"]),
        Paragraph(datetime.now().strftime("Generated %Y-%m-%d %H:%M"), styles["Normal"]),
        Spacer(1, 12),
    ]

    table_data = [report.headers] + report.rows
    table = Table(table_data, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDD5C0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F1E7")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)


def export_table_excel(report: TableReport, file_path: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = report.title[:31]  # Excel sheet-name length limit

    sheet.append(report.headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for row in report.rows:
        sheet.append(row)

    for column_cells in sheet.columns:
        longest = max((len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells), default=0)
        sheet.column_dimensions[column_cells[0].column_letter].width = longest + 4

    workbook.save(file_path)


def build_table_report_html(report: TableReport) -> str:
    header_cells = "".join(f"<th>{header}</th>" for header in report.headers)
    row_html = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in report.rows
    )
    return f"""
    <h2>{report.title}</h2>
    <p>Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    <table border="1" cellspacing="0" cellpadding="6" width="100%">
    <tr>{header_cells}</tr>
    {row_html}
    </table>
    """

FUEL_SUMMARY_HEADER = [
    "Fuel Type",
    "Tanks",
    "Capacity (L)",
    "Current Stock (L)",
    "Active Nozzles",
    "Total Nozzles",
    "Latest Variance %",
    "Classification",
]


def _fuel_summary_rows(summaries: Sequence[FuelTypeSummary]) -> List[List[str]]:
    rows = []
    for summary in summaries:
        rows.append(
            [
                summary.fuel_type,
                str(summary.tank_count),
                f"{summary.total_capacity:.2f}",
                f"{summary.total_current_stock:.2f}",
                str(summary.active_nozzle_count),
                str(summary.nozzle_count),
                f"{summary.latest_variance_percent:+.2f}" if summary.latest_variance_percent is not None else "—",
                (summary.latest_variance_classification or "—").replace("_", " ").title(),
            ]
        )
    return rows


def export_fuel_summary_pdf(summaries: Sequence[FuelTypeSummary], file_path: str) -> None:
    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("Fuel Type Summary", styles["Title"]),
        Paragraph(datetime.now().strftime("Generated %Y-%m-%d %H:%M"), styles["Normal"]),
        Spacer(1, 12),
    ]

    table_data = [FUEL_SUMMARY_HEADER] + _fuel_summary_rows(summaries)
    table = Table(table_data, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDD5C0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F1E7")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)


def export_fuel_summary_excel(summaries: Sequence[FuelTypeSummary], file_path: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Fuel Type Summary"

    sheet.append(FUEL_SUMMARY_HEADER)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for summary in summaries:
        sheet.append(
            [
                summary.fuel_type,
                summary.tank_count,
                float(summary.total_capacity),
                float(summary.total_current_stock),
                summary.active_nozzle_count,
                summary.nozzle_count,
                float(summary.latest_variance_percent) if summary.latest_variance_percent is not None else None,
                (summary.latest_variance_classification or "").replace("_", " ").title(),
            ]
        )

    for column_cells in sheet.columns:
        longest = max((len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells), default=0)
        sheet.column_dimensions[column_cells[0].column_letter].width = longest + 4

    workbook.save(file_path)
