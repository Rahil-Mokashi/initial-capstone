"""Landing-dashboard KPI summary — a computed view, nothing persisted.

Mirrors ReportService's pattern (services/report_service.py): read-only
aggregation over existing repositories, gated section-by-section on the
same permissions each underlying module already uses, so a user only ever
sees numbers for what they're allowed to open.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Optional

from app.core.constants import (
    DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT,
    Permission,
    PurchaseOrderStatus,
    SaleStatus,
    ShiftStatus,
)
from app.repositories.purchase_order_repository import PurchaseOrderRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.tank_repository import TankRepository
from app.services.auth_service import AuthService


@dataclass
class DashboardSummary:
    """Every field is None when the acting user lacks the permission that
    module is gated on - the UI renders only the stats it receives, the
    same "just don't show it" pattern used for the dashboard's own cards."""

    sales_today_count: Optional[int] = None
    sales_today_amount: Optional[Decimal] = None
    open_shifts_count: Optional[int] = None
    low_stock_tanks_count: Optional[int] = None
    pending_purchase_orders_count: Optional[int] = None


def _local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Local calendar day -> naive-UTC instant bounds, matching the fix
    already applied to TankTransactionRepository.sum_for_tank_by_type: a
    naive local boundary compared directly against a UTC-stored timestamp
    silently drops records recorded after local midnight whenever local
    time runs ahead of UTC. SQLite/SQLAlchemy returns DateTime columns as
    naive datetimes (representing UTC) on read, so the bounds are stripped
    of tzinfo after conversion to compare cleanly against them in Python."""

    local_start = datetime.combine(day, time.min).astimezone()
    local_end = datetime.combine(day, time.max).astimezone()
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


class DashboardService:
    def __init__(
        self,
        sale_repo: SaleRepository,
        shift_repo: ShiftRepository,
        tank_repo: TankRepository,
        purchase_order_repo: PurchaseOrderRepository,
        auth_service: AuthService,
    ):
        self._sale_repo = sale_repo
        self._shift_repo = shift_repo
        self._tank_repo = tank_repo
        self._purchase_order_repo = purchase_order_repo
        self._auth_service = auth_service

    def get_summary(self, actor_user_id: str) -> DashboardSummary:
        summary = DashboardSummary()
        can = lambda permission: self._auth_service.check_permission(actor_user_id, permission.value)  # noqa: E731

        if can(Permission.SALE_VIEW):
            day_start_utc, day_end_utc = _local_day_bounds_utc(date.today())
            todays_sales = [
                sale
                for sale in self._sale_repo.list_all()
                if sale.status == SaleStatus.COMPLETED.value and day_start_utc <= sale.sale_at <= day_end_utc
            ]
            summary.sales_today_count = len(todays_sales)
            summary.sales_today_amount = sum((sale.amount for sale in todays_sales), Decimal("0"))

        if can(Permission.SHIFT_VIEW):
            todays_shifts = self._shift_repo.list_for_date_range(date.today(), date.today())
            summary.open_shifts_count = sum(1 for shift in todays_shifts if shift.status == ShiftStatus.OPEN.value)

        if can(Permission.INVENTORY_VIEW):
            low_stock_count = 0
            for tank in self._tank_repo.list_all():
                if tank.capacity and tank.capacity > 0:
                    stock_percent = (tank.current_stock / tank.capacity) * 100
                    if stock_percent <= Decimal(str(DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT)):
                        low_stock_count += 1
            summary.low_stock_tanks_count = low_stock_count

        if can(Permission.PROCUREMENT_VIEW):
            pending_statuses = {PurchaseOrderStatus.DRAFT.value, PurchaseOrderStatus.PLACED.value, PurchaseOrderStatus.PARTIALLY_DELIVERED.value}
            summary.pending_purchase_orders_count = sum(
                1 for po in self._purchase_order_repo.list_all() if po.status in pending_statuses
            )

        return summary
