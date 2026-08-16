"""Business performance and sales-forecast analytics (user-requested
2026-08-16: period reports - daily/weekly/monthly/quarterly/yearly -
showing profitability per fuel type, plus a prediction of whether next
week's sales look like a hike or a dip).

Deliberately built with plain Python (no numpy/scikit-learn - this is
an offline desktop app with a small dependency footprint) using a
simple least-squares linear trend over recent weekly totals. This is
explainable and auditable rather than a black-box model: every number
shown traces back to a specific formula, matching the project's
"never silently change/derive financial data without a clear rule"
principle applied to a predictive feature.

Profitability assumption (recorded per CLAUDE.md's "ask/record
assumptions before implementing", since the underlying data doesn't
support a more precise method): estimated cost of goods uses the
weighted-average purchase cost for that fuel type as of the period end
(all PurchaseOrderItems for that fuel up to that date, quantity-
weighted) - not true FIFO/LIFO lot matching, which this app's data
model doesn't track. This is the same Weighted Average Cost (WAC)
method many small retailers use. When no purchase history exists for a
fuel type yet, profit figures are left as None ("not available") rather
than fabricated as zero or guessed.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from app.core.constants import (
    FORECAST_MIN_WEEKS_OF_HISTORY,
    FORECAST_TREND_THRESHOLD_PERCENT,
    Permission,
    SaleStatus,
)
from app.core.dates import PeriodType, period_bounds, period_bounds_utc
from app.core.permissions import require_permission


@dataclass
class FuelPeriodPerformance:
    fuel_type: str
    revenue: Decimal
    quantity_sold: Decimal
    weighted_avg_cost: Optional[Decimal] = None
    estimated_cost_of_goods: Optional[Decimal] = None
    estimated_gross_profit: Optional[Decimal] = None
    gross_margin_percent: Optional[Decimal] = None


@dataclass
class PeriodPerformanceReport:
    period_type: str
    period_start: date
    period_end: date
    fuel_breakdown: List[FuelPeriodPerformance] = field(default_factory=list)
    total_revenue: Decimal = Decimal("0")
    total_estimated_gross_profit: Optional[Decimal] = None
    total_expenses: Decimal = Decimal("0")
    estimated_net_profit: Optional[Decimal] = None


@dataclass
class FuelSalesForecast:
    fuel_type: str
    weekly_quantities: List[Tuple[date, Decimal]]
    trend: str  # "increasing" | "decreasing" | "stable" | "insufficient_data"
    explanation: str
    predicted_next_week_quantity: Optional[Decimal] = None
    predicted_next_week_revenue: Optional[Decimal] = None
    trend_percent: Optional[Decimal] = None


def _linear_trend(values: List[Decimal]) -> Tuple[float, float]:
    """Least-squares slope/intercept for y = slope*x + intercept, with
    x = 0..n-1 over the given values in order. Pure Python - no numpy,
    to keep this offline desktop app's dependency footprint small."""

    n = len(values)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = float(sum(values)) / n
    numerator = sum((x - x_mean) * (float(y) - y_mean) for x, y in zip(xs, values))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return 0.0, y_mean
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept


class AnalyticsService:
    def __init__(self, sale_repo, expense_repo, purchase_order_item_repo, fuel_repo, auth_service):
        self._sale_repo = sale_repo
        self._expense_repo = expense_repo
        self._purchase_order_item_repo = purchase_order_item_repo
        self._fuel_repo = fuel_repo
        self._auth_service = auth_service

    @require_permission(Permission.ANALYTICS_VIEW.value)
    def get_period_performance(self, actor_user_id: str, period_type: PeriodType, reference_date: date) -> PeriodPerformanceReport:
        start_date, end_date = period_bounds(period_type, reference_date)
        start_utc, end_utc = period_bounds_utc(period_type, reference_date)

        sales = [
            s for s in self._sale_repo.list_all()
            if s.status == SaleStatus.COMPLETED.value and start_utc <= s.sale_at <= end_utc
        ]
        expenses = [
            e for e in self._expense_repo.list_all()
            if e.status == "approved" and start_date <= e.expense_date <= end_date
        ]

        breakdown = []
        for fuel in self._fuel_repo.list_active():
            fuel_sales = [s for s in sales if s.fuel_id == fuel.id]
            if not fuel_sales:
                continue

            revenue = sum((s.amount for s in fuel_sales), Decimal("0"))
            quantity = sum((s.quantity for s in fuel_sales), Decimal("0"))
            avg_cost = self._weighted_average_cost(fuel.id, end_date)

            cost_of_goods = gross_profit = margin_percent = None
            if avg_cost is not None:
                cost_of_goods = (avg_cost * quantity).quantize(Decimal("0.01"))
                gross_profit = (revenue - cost_of_goods).quantize(Decimal("0.01"))
                margin_percent = ((gross_profit / revenue * 100) if revenue else Decimal("0")).quantize(Decimal("0.01"))

            breakdown.append(
                FuelPeriodPerformance(
                    fuel_type=fuel.fuel_type,
                    revenue=revenue,
                    quantity_sold=quantity,
                    weighted_avg_cost=avg_cost,
                    estimated_cost_of_goods=cost_of_goods,
                    estimated_gross_profit=gross_profit,
                    gross_margin_percent=margin_percent,
                )
            )

        total_revenue = sum((b.revenue for b in breakdown), Decimal("0"))
        total_expenses = sum((e.amount for e in expenses), Decimal("0"))

        known_profits = [b.estimated_gross_profit for b in breakdown if b.estimated_gross_profit is not None]
        total_gross_profit = sum(known_profits, Decimal("0")) if len(known_profits) == len(breakdown) and breakdown else None
        net_profit = (total_gross_profit - total_expenses) if total_gross_profit is not None else None

        return PeriodPerformanceReport(
            period_type=period_type.value,
            period_start=start_date,
            period_end=end_date,
            fuel_breakdown=breakdown,
            total_revenue=total_revenue,
            total_estimated_gross_profit=total_gross_profit,
            total_expenses=total_expenses,
            estimated_net_profit=net_profit,
        )

    def _weighted_average_cost(self, fuel_id: str, as_of_date: date) -> Optional[Decimal]:
        items = [
            item for item in self._purchase_order_item_repo.list_all()
            if item.fuel_id == fuel_id and item.purchase_order and item.purchase_order.order_date <= as_of_date
        ]
        total_quantity = sum((item.quantity_ordered for item in items), Decimal("0"))
        if total_quantity == 0:
            return None
        total_cost = sum((item.quantity_ordered * item.rate_per_liter for item in items), Decimal("0"))
        return (total_cost / total_quantity).quantize(Decimal("0.01"))

    @require_permission(Permission.ANALYTICS_VIEW.value)
    def get_sales_forecast(self, actor_user_id: str, weeks_of_history: int = 8) -> List[FuelSalesForecast]:
        today = date.today()
        return [
            self._forecast_for_fuel(fuel, today, weeks_of_history)
            for fuel in self._fuel_repo.list_active()
        ]

    def _forecast_for_fuel(self, fuel, today: date, weeks_of_history: int) -> FuelSalesForecast:
        sales = [s for s in self._sale_repo.list_all() if s.fuel_id == fuel.id and s.status == SaleStatus.COMPLETED.value]

        weekly: List[Tuple[date, Decimal]] = []
        for weeks_ago in range(weeks_of_history - 1, -1, -1):
            week_reference = today - timedelta(weeks=weeks_ago)
            week_start, _ = period_bounds(PeriodType.WEEK, week_reference)
            week_start_utc, week_end_utc = period_bounds_utc(PeriodType.WEEK, week_reference)
            week_total = sum(
                (s.quantity for s in sales if week_start_utc <= s.sale_at <= week_end_utc), Decimal("0")
            )
            weekly.append((week_start, week_total))

        active_weeks = sum(1 for _, quantity in weekly if quantity > 0)
        if active_weeks < FORECAST_MIN_WEEKS_OF_HISTORY:
            return FuelSalesForecast(
                fuel_type=fuel.fuel_type,
                weekly_quantities=weekly,
                trend="insufficient_data",
                explanation=(
                    f"Not enough sales history for {fuel.fuel_type} yet - at least "
                    f"{FORECAST_MIN_WEEKS_OF_HISTORY} weeks of activity are needed before a forecast is shown."
                ),
            )

        quantities = [quantity for _, quantity in weekly]
        slope, intercept = _linear_trend(quantities)
        predicted_quantity_raw = slope * len(quantities) + intercept
        predicted_quantity = Decimal(str(max(0.0, predicted_quantity_raw))).quantize(Decimal("0.001"))

        last_actual = quantities[-1]
        if last_actual > 0:
            change_percent = (predicted_quantity - last_actual) / last_actual * 100
        else:
            change_percent = Decimal("0")

        if change_percent > Decimal(str(FORECAST_TREND_THRESHOLD_PERCENT)):
            trend = "increasing"
            explanation = (
                f"{fuel.fuel_type} sales have been trending up over the last {weeks_of_history} weeks; "
                f"next week is projected around {predicted_quantity:.0f} L, about {change_percent:.1f}% "
                "more than last week - a likely hike."
            )
        elif change_percent < -Decimal(str(FORECAST_TREND_THRESHOLD_PERCENT)):
            trend = "decreasing"
            explanation = (
                f"{fuel.fuel_type} sales have been trending down over the last {weeks_of_history} weeks; "
                f"next week is projected around {predicted_quantity:.0f} L, about {abs(change_percent):.1f}% "
                "less than last week - a possible dip."
            )
        else:
            trend = "stable"
            explanation = (
                f"{fuel.fuel_type} sales have been steady over the last {weeks_of_history} weeks; "
                f"next week is projected around {predicted_quantity:.0f} L, close to last week's level."
            )

        return FuelSalesForecast(
            fuel_type=fuel.fuel_type,
            weekly_quantities=weekly,
            trend=trend,
            explanation=explanation,
            predicted_next_week_quantity=predicted_quantity,
            predicted_next_week_revenue=(predicted_quantity * fuel.rate_per_liter).quantize(Decimal("0.01")),
            trend_percent=change_percent.quantize(Decimal("0.01")),
        )
