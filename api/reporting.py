"""Turns a TableReport into the four things every report screen offers: printable HTML, PDF, Excel, CSV.
Uses the Qt app's own builders/exporters (app/services/report_export.py) unchanged."""

import os
import re
import tempfile
from typing import Literal

from fastapi import Response

from api.schemas import Out
from app.services.report_export import build_table_report_html, export_table_csv, export_table_excel, export_table_pdf
from app.services.report_service import TableReport

Kind = Literal["pdf", "xlsx", "csv"]

_EXPORTERS = {"pdf": (export_table_pdf, "application/pdf"), "xlsx": (export_table_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), "csv": (export_table_csv, "text/csv; charset=utf-8")}


class ReportView(Out):
    """What a table report looks like on screen, plus its printable HTML (the same one Qt previews)."""

    title: str
    headers: list[str]
    rows: list[list[str]]
    # Column positions that hold money / litres, so the table can right-align them like Qt does.
    money_columns: list[int] = []
    volume_columns: list[int] = []
    html: str


def view(report: TableReport, company=None) -> ReportView:
    return ReportView(
        title=report.title,
        headers=list(report.headers),
        rows=[[("" if c is None else str(c)) for c in row] for row in report.rows],
        money_columns=sorted(getattr(report, "money_columns", ())),
        volume_columns=sorted(getattr(report, "volume_columns", ())),
        html=build_table_report_html(report, company),
    )


def file_name(report: TableReport, kind: Kind) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", report.title).strip("_").lower() or "report"
    return f"{stem}.{kind}"


def file_response(report: TableReport, kind: Kind) -> Response:
    exporter, media_type = _EXPORTERS[kind]
    fd, path = tempfile.mkstemp(suffix=f".{kind}")
    os.close(fd)
    try:
        exporter(report, path)
        with open(path, "rb") as f:
            data = f.read()
    finally:
        os.remove(path)
    return Response(content=data, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{file_name(report, kind)}"'})
