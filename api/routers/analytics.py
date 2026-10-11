"""Business Insights: period performance and the sales forecast.
Same AnalyticsService calls as app/ui/analytics_window.py. The two TableReport builders below are copies of the
ones that live inside that Qt window (it cannot be imported here: it pulls in PySide6)."""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response

from api import reporting
from api.deps import CurrentUser, current_user, get_services
from api.schemas import Out
from api.services import Services
from app.core.dates import PeriodType
from app.services.report_export import build_table_report_html
from app.services.report_service import TableReport

router = APIRouter(tags=["analytics"])

TREND_LABELS = {
    "increasing": "▲ Likely hike",
    "decreasing": "▼ Possible dip",
    "stable": "▬ Stable",
    "insufficient_data": "Not enough data",
}


def performance_report(report) -> TableReport:
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
    rows.append(
        [
            "Total Est. Gross Profit",
            f"{report.total_estimated_gross_profit:.2f}" if report.total_estimated_gross_profit is not None else "N/A",
            "", "", "", "", "",
        ]
    )
    rows.append(["Total Approved Expenses", f"{report.total_expenses:.2f}", "", "", "", "", ""])
    rows.append(
        ["Est. Net Profit", f"{report.estimated_net_profit:.2f}" if report.estimated_net_profit is not None else "N/A", "", "", "", "", ""]
    )
    title = f"Business Performance - {report.period_type.title()} ({report.period_start} to {report.period_end})"
    return TableReport(title=title, headers=headers, rows=rows)


def forecast_report(forecasts) -> TableReport:
    headers = ["Fuel Type", "Trend", "Predicted Next Week (L)", "Predicted Revenue", "Change vs Last Week"]
    rows = [
        [
            f.fuel_type,
            TREND_LABELS.get(f.trend, f.trend),
            f"{f.predicted_next_week_quantity:.2f}" if f.predicted_next_week_quantity is not None else "N/A",
            f"{f.predicted_next_week_revenue:.2f}" if f.predicted_next_week_revenue is not None else "N/A",
            f"{f.trend_percent:+.1f}%" if f.trend_percent is not None else "N/A",
        ]
        for f in forecasts
    ]
    return TableReport(title="Sales Forecast", headers=headers, rows=rows)


class ForecastOut(Out):
    report: reporting.ReportView
    # One plain-language paragraph per fuel, shown under the table and printed after it.
    explanations: list[str]


def _forecast_html(forecasts) -> str:
    return build_table_report_html(forecast_report(forecasts)) + "<p>" + "</p><p>".join(f.explanation for f in forecasts) + "</p>"


@router.get("/analytics/performance", response_model=reporting.ReportView)
def performance(
    period: PeriodType = PeriodType.DAY,
    as_of: Optional[date] = None,
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
):
    result = services.analytics.get_period_performance(user.id, period, as_of or date.today())
    return reporting.view(performance_report(result))


@router.get("/analytics/performance/export.{kind}")
def performance_export(
    kind: Literal["pdf", "xlsx", "csv"],
    period: PeriodType = PeriodType.DAY,
    as_of: Optional[date] = None,
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
) -> Response:
    result = services.analytics.get_period_performance(user.id, period, as_of or date.today())
    return reporting.file_response(performance_report(result), kind)


@router.get("/analytics/forecast", response_model=ForecastOut)
def forecast(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    forecasts = services.analytics.get_sales_forecast(user.id)
    view = reporting.view(forecast_report(forecasts))
    view.html = _forecast_html(forecasts)  # Qt prints the explanations after the table
    return ForecastOut(report=view, explanations=[f.explanation for f in forecasts])


@router.get("/analytics/forecast/export.{kind}")
def forecast_export(
    kind: Literal["pdf", "xlsx", "csv"], user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
) -> Response:
    return reporting.file_response(forecast_report(services.analytics.get_sales_forecast(user.id)), kind)
