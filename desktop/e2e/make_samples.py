"""Produces the SAME HTML the Qt app prints, using its real builders, for the printing spike.

    python desktop/e2e/make_samples.py <output-dir>

writes report.html (build_table_report_html) and receipt.html (build_sale_receipt_html).
Only formatting code from app/services/report_export.py runs; no database is opened.
"""

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.report_export import build_sale_receipt_html, build_table_report_html  # noqa: E402
from app.services.report_service import TableReport  # noqa: E402


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    report = TableReport(
        title="Tank stock report",
        headers=["Tank", "Fuel", "Capacity (L)", "Stock (L)", "Level"],
        rows=[
            ["T1", "Petrol", "10,000.000", "2,500.500", "25.0%"],
            ["T2", "Diesel", "10,000.000", "1,800.000", "18.0%"],
        ]
        + [[f"T{i}", "Power", "5,000.000", f"{i * 100}.000", "-"] for i in range(3, 40)],
    )
    (out / "report.html").write_text(build_table_report_html(report), encoding="utf-8")

    sale = SimpleNamespace(
        receipt_number="R-000123",
        sale_at=datetime(2026, 10, 9, 14, 5),
        fuel=SimpleNamespace(fuel_type="Petrol"),
        nozzle=SimpleNamespace(code="N1"),
        quantity=12.5,
        rate_per_liter=104.55,
        amount=1306.88,
        payment_method="upi",
        customer=None,
    )
    payment = SimpleNamespace(reference_number="UPI-998877")
    receipt = build_sale_receipt_html(sale, payment)
    # A thermal roll is ~72 mm of printable width: the same document, narrower.
    narrow = (
        "<style>@page{size:80mm 160mm;margin:3mm}body{width:74mm;font:11px Arial}"
        "table{width:100%;border-collapse:collapse}td{padding:2px;border-bottom:1px dotted #000}"
        "h2,h3{margin:2px 0;text-align:center}</style>" + receipt
    )
    (out / "receipt.html").write_text(narrow, encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
