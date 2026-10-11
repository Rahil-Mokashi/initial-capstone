"""Reports hub and the shared table-report screen.
Same ReportService calls as app/ui/report_window.py and app/ui/table_report_window.py; the printable HTML and
the PDF / Excel / CSV files come from the Qt exporters unchanged (api/reporting.py)."""

from datetime import date
from typing import Callable, Literal, NamedTuple, Optional

from fastapi import APIRouter, Depends, Response

from api import reporting
from api.deps import CurrentUser, current_user, get_services
from api.errors import ApiError
from api.schemas import Out
from api.services import Services
from app.core.constants import Permission
from app.services.report_export import fuel_summary_to_table_report

router = APIRouter(tags=["reports"])


class Spec(NamedTuple):
    key: str
    label: str
    permission: Permission
    fetch: Callable[[Services], Callable]
    dates: bool = False
    filters: tuple = ()  # "employee", "nozzle"


def _fuel_summary(services: Services):
    return lambda actor, **_: fuel_summary_to_table_report(services.reports.get_fuel_type_summary(actor))


# Same list and order as the Qt reports hub; each report is shown only to users holding its permission.
CATALOG: list[Spec] = [
    Spec("fuel_type_summary", "Fuel Type Summary", Permission.INVENTORY_VIEW, _fuel_summary),
    Spec("sales_report", "Sales Report", Permission.SALE_VIEW, lambda s: s.reports.get_sales_report, dates=True),
    Spec("payment_summary_report", "Payment Summary Report", Permission.SALE_VIEW, lambda s: s.reports.get_payment_summary_report, dates=True),
    Spec("expense_summary_report", "Expense Summary Report", Permission.EXPENSE_VIEW, lambda s: s.reports.get_expense_summary_report, dates=True),
    Spec("credit_fuel_type_report", "Credit Report by Fuel Type", Permission.CREDIT_VIEW, lambda s: s.reports.get_credit_fuel_type_report),
    Spec("customer_outstanding_report", "Customer Outstanding Report", Permission.CREDIT_VIEW, lambda s: s.reports.get_customer_outstanding_report),
    Spec("reconciliation_report", "Shift Reconciliation Report", Permission.RECONCILIATION_VIEW, lambda s: s.reports.get_reconciliation_report, dates=True),
    Spec("daily_summary_report", "Daily Summary Report", Permission.SALE_VIEW, lambda s: s.reports.get_daily_summary_report, dates=True),
    Spec(
        "attendant_nozzle_report",
        "Attendant & Nozzle Report",
        Permission.SALE_VIEW,
        lambda s: s.reports.get_attendant_nozzle_report,
        dates=True,
        filters=("employee", "nozzle"),
    ),
    Spec("fuel_movement_report", "Fuel Movement Report", Permission.INVENTORY_VIEW, lambda s: s.reports.get_fuel_movement_report, dates=True),
    Spec("cash_book", "Cash Book", Permission.EXPENSE_VIEW, lambda s: s.reports.get_cash_book_report, dates=True),
    Spec(
        "attendance_report",
        "Attendance Report",
        Permission.ATTENDANCE_VIEW,
        lambda s: s.reports.get_attendance_report,
        dates=True,
        filters=("employee",),
    ),
]
BY_KEY = {s.key: s for s in CATALOG}


class ReportEntry(Out):
    key: str
    label: str
    dates: bool
    filters: list[str]


class Hub(Out):
    reports: list[ReportEntry]
    # Business Insights lives on its own screen; the hub only needs to know whether to link to it.
    insights: bool


class Choice(Out):
    label: str
    value: str


class FilterOptions(Out):
    employees: list[Choice]
    nozzles: list[Choice]


class FuelCard(Out):
    fuel_type: str
    tank_count: int
    total_capacity: str
    total_current_stock: str
    nozzle_count: int
    active_nozzle_count: int
    latest_variance_percent: Optional[str] = None
    latest_variance_classification: Optional[str] = None


@router.get("/reports", response_model=Hub)
def hub(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    entries = [
        ReportEntry(key=s.key, label=s.label, dates=s.dates, filters=list(s.filters))
        for s in CATALOG
        if services.auth.check_permission(user.id, s.permission.value)
    ]
    return Hub(reports=entries, insights=services.auth.check_permission(user.id, Permission.ANALYTICS_VIEW.value))


@router.get("/reports/filter-options", response_model=FilterOptions)
def filter_options(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    o = services.reports.get_report_filter_options(user.id)
    return FilterOptions(
        employees=[Choice(label=d, value=v) for d, v in o.get("employees", [])],
        nozzles=[Choice(label=d, value=v) for d, v in o.get("nozzles", [])],
    )


@router.get("/reports/fuel-type-summary/cards", response_model=list[FuelCard])
def fuel_cards(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [
        FuelCard(
            fuel_type=s.fuel_type,
            tank_count=s.tank_count,
            total_capacity=f"{s.total_capacity:.3f}",
            total_current_stock=f"{s.total_current_stock:.3f}",
            nozzle_count=s.nozzle_count,
            active_nozzle_count=s.active_nozzle_count,
            latest_variance_percent=f"{s.latest_variance_percent:+.2f}" if s.latest_variance_percent is not None else None,
            latest_variance_classification=s.latest_variance_classification,
        )
        for s in services.reports.get_fuel_type_summary(user.id)
    ]


def _build(key: str, services: Services, user_id: str, date_from, date_to, employee_id, nozzle_id):
    spec = BY_KEY.get(key)
    if spec is None:
        raise ApiError(404, "not_found", f"Unknown report: {key}")
    args: dict = {}
    if spec.dates:
        if date_from:
            args["date_from"] = date_from
        if date_to:
            args["date_to"] = date_to
    # Only choices that are actually set are passed, never employee_id=None as if it were a decision (as in Qt).
    if "employee" in spec.filters and employee_id:
        args["employee_id"] = employee_id
    if "nozzle" in spec.filters and nozzle_id:
        args["nozzle_id"] = nozzle_id
    return spec.fetch(services)(user_id, **args)


@router.get("/reports/{key}", response_model=reporting.ReportView)
def run_report(
    key: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    employee_id: Optional[str] = None,
    nozzle_id: Optional[str] = None,
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
):
    return reporting.view(_build(key, services, user.id, date_from, date_to, employee_id, nozzle_id), services.settings.get_company_profile())


@router.get("/reports/{key}/export.{kind}")
def export_report(
    key: str,
    kind: Literal["pdf", "xlsx", "csv"],
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    employee_id: Optional[str] = None,
    nozzle_id: Optional[str] = None,
    user: CurrentUser = Depends(current_user),
    services: Services = Depends(get_services),
) -> Response:
    # Re-fetched here, not reused from the screen, so an export always matches the filters sent with it.
    return reporting.file_response(_build(key, services, user.id, date_from, date_to, employee_id, nozzle_id), kind)
