"""Landing-dashboard KPI summary — a computed view, nothing persisted.

Mirrors ReportService's pattern (services/report_service.py): read-only
aggregation over existing repositories, gated section-by-section on the
same permissions each underlying module already uses, so a user only ever
sees numbers for what they're allowed to open.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from app.core.constants import (
    DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT,
    Permission,
    PurchaseOrderStatus,
    SaleStatus,
    ShiftStatus,
)
from app.core.dates import local_day_bounds_utc
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
            day_start_utc, day_end_utc = local_day_bounds_utc(date.today())
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

    def get_recent_daily_sales(self, actor_user_id: str, days: int = 7) -> List[Tuple[date, Decimal]]:
        """Total COMPLETED sale revenue for each of the last `days` local
        calendar days (oldest first), for the dashboard's sales-trend
        chart. Gated on SALE_VIEW like every other sales figure this
        service returns; an empty list for a user without that permission
        rather than raising, matching get_summary's "just don't show it"
        pattern.

        Fetches every sale once (`list_all()`, the same call get_summary's
        own today's-sales figure already makes) rather than one query per
        day - at this app's documented sales volume that is a few thousand
        rows even at 30 days, trivial to filter in Python, and one query
        instead of up to thirty.
        """
        if not self._auth_service.check_permission(actor_user_id, Permission.SALE_VIEW.value):
            return []

        all_sales = self._sale_repo.list_all()
        completed = [sale for sale in all_sales if sale.status == SaleStatus.COMPLETED.value]

        series: List[Tuple[date, Decimal]] = []
        for offset in range(days - 1, -1, -1):
            day = date.today() - timedelta(days=offset)
            day_start_utc, day_end_utc = local_day_bounds_utc(day)
            total = sum(
                (sale.amount for sale in completed if day_start_utc <= sale.sale_at <= day_end_utc),
                Decimal("0"),
            )
            series.append((day, total))
        return series
