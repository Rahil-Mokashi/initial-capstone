"""PDF/Excel/CSV export for reports (CLAUDE.md Reporting Rules: every
important report must support Print, Print Preview, PDF export, and
Excel export). Pure formatting functions - the caller fetches data
through a permission-checked service method first; nothing here
touches the database or checks permissions.
"""

import csv
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


def export_table_csv(report: TableReport, file_path: str) -> None:
    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(report.headers)
        writer.writerows(report.rows)


def export_sale_receipt_pdf(sale, payment, file_path: str) -> None:
    """A printable customer receipt for one Sale (problemstatement.md
    #16 - "Generate sales receipts", noted as deferred to Phase 17 when
    Phase 11 Sales was built). Deliberately a compact, receipt-shaped
    layout, not the tabular TableReport shape every other export in
    this module produces."""

    doc = SimpleDocTemplate(file_path, pagesize=A4, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("Petrol Pump ERP", styles["Title"]),
        Paragraph(f"Receipt {sale.receipt_number}", styles["Heading2"]),
        Paragraph(sale.sale_at.strftime("%Y-%m-%d %H:%M"), styles["Normal"]),
        Spacer(1, 12),
    ]

    rows = [
        ["Fuel Type", sale.fuel.fuel_type if sale.fuel else ""],
        ["Nozzle", sale.nozzle.code if sale.nozzle else ""],
        ["Quantity (L)", f"{sale.quantity:.2f}"],
        ["Rate / Litre", f"{sale.rate_per_liter:.2f}"],
        ["Amount", f"{sale.amount:.2f}"],
        ["Payment Method", sale.payment_method.title()],
    ]
    if sale.customer:
        rows.append(["Customer", sale.customer.name])
    if payment and payment.reference_number:
        rows.append(["Reference", payment.reference_number])

    table = Table(rows, hAlign="LEFT", colWidths=[140, 260])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDD5C0")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Thank you for your business.", styles["Normal"]))
    doc.build(elements)


def build_letterhead_html(company=None) -> str:
    """The business identity that heads a printed document.

    Optional on purpose. Passing None falls back to the application name,
    so every existing caller keeps working and a pump that has not filled
    in Settings yet still gets a usable document - just an anonymous one.
    The Settings screen warns about that rather than this function
    refusing to print.
    """
    if company is None or not getattr(company, "has_company_profile", False):
        return "<h2>Petrol Pump ERP</h2>"

    lines = [f"<h2>{company.company_name}</h2>"]
    address = "<br/>".join(company.address_lines())
    if address:
        lines.append(f"<p>{address}</p>")

    contact = " &nbsp;|&nbsp; ".join(
        part for part in (
            f"Phone: {company.phone}" if company.phone else "",
            f"Email: {company.email}" if company.email else "",
        ) if part
    )
    if contact:
        lines.append(f"<p>{contact}</p>")

    statutory = " &nbsp;|&nbsp; ".join(
        part for part in (
            f"GSTIN: {company.gst_number}" if company.gst_number else "",
            f"Licence: {company.licence_number}" if company.licence_number else "",
        ) if part
    )
    if statutory:
        lines.append(f"<p>{statutory}</p>")
    return "".join(lines)


def build_sale_receipt_html(sale, payment, company=None) -> str:
    rows = [
        ("Fuel Type", sale.fuel.fuel_type if sale.fuel else ""),
        ("Nozzle", sale.nozzle.code if sale.nozzle else ""),
        ("Quantity (L)", f"{sale.quantity:.2f}"),
        ("Rate / Litre", f"{sale.rate_per_liter:.2f}"),
        ("Amount", f"{sale.amount:.2f}"),
        ("Payment Method", sale.payment_method.title()),
    ]
    if sale.customer:
        rows.append(("Customer", sale.customer.name))
    if payment and payment.reference_number:
        rows.append(("Reference", payment.reference_number))

    row_html = "".join(f"<tr><td><b>{label}</b></td><td>{value}</td></tr>" for label, value in rows)
    footer = "Thank you for your business."
    if company is not None and getattr(company, "receipt_footer", None):
        footer = company.receipt_footer
    return f"""
    {build_letterhead_html(company)}
    <h3>Receipt {sale.receipt_number}</h3>
    <p>{sale.sale_at.strftime('%Y-%m-%d %H:%M')}</p>
    <table border="1" cellspacing="0" cellpadding="6" width="100%">{row_html}</table>
    <p>{footer}</p>
    """


def build_table_report_html(report: TableReport, company=None) -> str:
    header_cells = "".join(f"<th>{header}</th>" for header in report.headers)
    row_html = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in report.rows
    )
    return f"""
    {build_letterhead_html(company)}
    <h3>{report.title}</h3>
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
