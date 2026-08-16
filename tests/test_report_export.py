from decimal import Decimal

import openpyxl
import pytest
from pypdf import PdfReader

from app.services.report_export import export_fuel_summary_excel, export_fuel_summary_pdf
from app.services.report_service import FuelTypeSummary


@pytest.fixture()
def summaries():
    return [
        FuelTypeSummary(
            fuel_type="Petrol",
            fuel_id="f1",
            tank_count=2,
            total_capacity=Decimal("20000.000"),
            total_current_stock=Decimal("15000.500"),
            nozzle_count=4,
            active_nozzle_count=3,
            latest_variance_percent=Decimal("0.750"),
            latest_variance_classification="normal",
        ),
        FuelTypeSummary(
            fuel_type="Diesel",
            fuel_id="f2",
            tank_count=1,
            total_capacity=Decimal("10000.000"),
            total_current_stock=Decimal("4000.000"),
            nozzle_count=2,
            active_nozzle_count=2,
            latest_variance_percent=None,
            latest_variance_classification=None,
        ),
    ]


def test_export_pdf_creates_a_readable_file(tmp_path, summaries):
    pdf_path = str(tmp_path / "fuel_summary.pdf")
    export_fuel_summary_pdf(summaries, pdf_path)

    reader = PdfReader(pdf_path)
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert "Petrol" in text
    assert "Diesel" in text


def test_export_excel_creates_expected_rows(tmp_path, summaries):
    xlsx_path = str(tmp_path / "fuel_summary.xlsx")
    export_fuel_summary_excel(summaries, xlsx_path)

    workbook = openpyxl.load_workbook(xlsx_path)
    sheet = workbook.active

    assert sheet["A1"].value == "Fuel Type"
    assert sheet["A2"].value == "Petrol"
    assert sheet["A3"].value == "Diesel"
    assert sheet.max_row == 3


def test_export_excel_handles_missing_variance(tmp_path, summaries):
    xlsx_path = str(tmp_path / "fuel_summary.xlsx")
    export_fuel_summary_excel(summaries, xlsx_path)

    workbook = openpyxl.load_workbook(xlsx_path)
    sheet = workbook.active

    diesel_row = sheet[3]
    variance_cell = diesel_row[6]
    assert variance_cell.value is None


def test_export_pdf_handles_empty_summary_list(tmp_path):
    pdf_path = str(tmp_path / "empty.pdf")
    export_fuel_summary_pdf([], pdf_path)

    reader = PdfReader(pdf_path)
    assert len(reader.pages) >= 1


def test_export_excel_handles_empty_summary_list(tmp_path):
    xlsx_path = str(tmp_path / "empty.xlsx")
    export_fuel_summary_excel([], xlsx_path)

    workbook = openpyxl.load_workbook(xlsx_path)
    sheet = workbook.active
    assert sheet.max_row == 1
