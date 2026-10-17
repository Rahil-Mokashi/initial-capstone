"""Dashboard (summary tiles, sales trend, who is on shift now) and the alerts list.
Same DashboardService / NotificationService / ShiftService calls as app/ui/main_window.py
and app/ui/notification_window.py."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyOut, Out
from api.services import Services
from app.core.constants import AssignmentStatus, ShiftStatus

router = APIRouter(tags=["dashboard"])


class SummaryOut(Out):
    """Every field is null when the signed-in user lacks the permission that module is gated on."""

    sales_today_count: Optional[int] = None
    sales_today_amount: Optional[MoneyOut] = None
    open_shifts_count: Optional[int] = None
    open_shift_labels: Optional[list[str]] = None
    low_stock_tanks_count: Optional[int] = None
    pending_purchase_orders_count: Optional[int] = None


class TrendPoint(Out):
    day: date
    amount: MoneyOut


class RosterRow(Out):
    name: str
    detail: str


class AlertEmployee(Out):
    id: str
    name: str


class AlertShortage(Out):
    line_id: str
    shift: str
    employees: list[AlertEmployee]
    suggested_employee_id: Optional[str] = None


class AlertOut(Out):
    key: str
    category: str
    severity: str
    title: str
    detail: str
    action: str
    entity_id: Optional[str] = None
    is_summary: bool
    count: int = 1
    shortage: Optional[AlertShortage] = None


class AlertsOut(Out):
    total: int
    critical_count: int
    warning_count: int
    notifications: list[AlertOut]


class AcknowledgeIn(In):
    key: str
    reason: str = ""


class MarkShortageIn(In):
    line_id: str
    employee_id: str


@router.get("/dashboard/summary", response_model=SummaryOut)
def summary(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.dashboard.get_summary(user.id)


@router.get("/dashboard/sales-trend", response_model=list[TrendPoint])
def sales_trend(days: int = Query(default=7, ge=1, le=90), user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [TrendPoint(day=d, amount=a) for d, a in services.dashboard.get_recent_daily_sales(user.id, days)]


@router.get("/dashboard/roster", response_model=list[RosterRow])
def roster(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """Who is on a nozzle right now across every shift open today (the roster card of the Qt dashboard)."""
    rows: list[RosterRow] = []
    for shift in services.shifts.list_shifts(user.id, date.today(), date.today()):
        if shift.status != ShiftStatus.OPEN.value:
            continue
        for a in shift.nozzle_assignments:
            if a.status != AssignmentStatus.ACTIVE.value:
                continue
            e = a.employee
            name = f"{e.first_name} {e.last_name}" if e else "Unknown employee"
            code = a.nozzle.code if a.nozzle else "?"
            fuel = a.nozzle.fuel.fuel_type if a.nozzle and a.nozzle.fuel else ""
            since = a.start_time.strftime("%H:%M") if a.start_time else "-"
            rows.append(RosterRow(name=name, detail=f"{code} · {fuel} · {shift.shift_label} · since {since}"))
    return sorted(rows, key=lambda r: r.name)


def _alerts_out(items) -> AlertsOut:
    out = []
    for i in items:
        n = i.notification
        sh = i.shortage
        out.append(AlertOut(
            key=i.key, category=n.category.value, severity=n.severity.value, title=n.title, detail=n.detail, action=n.action,
            entity_id=n.entity_id, is_summary=n.is_summary, count=i.count,
            shortage=AlertShortage(line_id=sh.line_id, shift=sh.shift_label, employees=[AlertEmployee(id=e, name=nm) for e, nm in sh.employees],
                                   suggested_employee_id=sh.suggested_employee_id) if sh else None,
        ))
    return AlertsOut(
        total=len(out), critical_count=sum(1 for a in out if a.severity == "critical"),
        warning_count=sum(1 for a in out if a.severity == "warning"), notifications=out,
    )


@router.get("/alerts", response_model=AlertsOut)
def alerts(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _alerts_out(services.alerts.list(user.id))


@router.post("/alerts/acknowledge", status_code=204)
def acknowledge(body: AcknowledgeIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.alerts.acknowledge(user.id, body.key, body.reason)


@router.post("/alerts/shortage", status_code=204)
def mark_shortage(body: MarkShortageIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """"Mark against <name>": books the shortage on that person (the same service the Reconciliation screen uses) and the alert resolves."""
    services.alerts.mark_shortage(user.id, body.line_id, body.employee_id)
