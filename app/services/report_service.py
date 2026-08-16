"""
Reporting service layer (problemstatement.md #25-32, Phase 16).

get_fuel_type_summary was the first, narrowly-scoped slice: an inventory
summary sectioned by fuel type (Petrol/Diesel/Power, or whatever fuel
types exist), per the user's explicit request that fuel data be reported
per fuel type rather than as one aggregate. The table-report methods
added since close out the specific "reports deferred to Phase 16" items
already promised by name in Phases 10-15's own docs (sales, payments,
credit/customer outstanding, expenses, reconciliation) rather than
attempting every report enumerated in problemstatement.md #25-32 - the
full list (daily/shift/attendant/HR/management reports, trend analysis,
etc.) is much larger and deliberately left for a later, dedicated pass.
All read-only aggregation over existing repositories; nothing here
writes data or invents a number that isn't derivable from what another
service already tracks.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission, PaymentMethod, PaymentStatus, SaleStatus
from app.core.dates import local_day_bounds_utc
from app.core.permissions import require_permission


@dataclass
class FuelTypeSummary:
    fuel_type: str
    fuel_id: str
    tank_count: int = 0
    total_capacity: Decimal = field(default_factory=lambda: Decimal("0"))
    total_current_stock: Decimal = field(default_factory=lambda: Decimal("0"))
    nozzle_count: int = 0
    active_nozzle_count: int = 0
    latest_variance_percent: Optional[Decimal] = None
    latest_variance_classification: Optional[str] = None


@dataclass
class TableReport:
    """A generic tabular report - title, column headers, and pre-formatted
    string rows. Shared by every report added for Phase 16 so the UI
    (TableReportWindow) and export layer (report_export.py) only need to
    be written once, not once per report."""

    title: str
    headers: List[str]
    rows: List[List[str]] = field(default_factory=list)


def _in_range(moment, start, end) -> bool:
    if start is not None and moment < start:
        return False
    if end is not None and moment > end:
        return False
    return True


class ReportService:
    def __init__(
        self,
        fuel_repo,
        tank_repo,
        nozzle_repo,
        reconciliation_repo,
        auth_service,
        sale_repo,
        payment_repo,
        expense_repo,
        credit_account_repo,
        customer_payment_repo,
        customer_repo,
        shift_reconciliation_repo,
    ):
        self._fuel_repo = fuel_repo
        self._tank_repo = tank_repo
        self._nozzle_repo = nozzle_repo
        self._reconciliation_repo = reconciliation_repo
        self._auth_service = auth_service
        self._sale_repo = sale_repo
        self._payment_repo = payment_repo
        self._expense_repo = expense_repo
        self._credit_account_repo = credit_account_repo
        self._customer_payment_repo = customer_payment_repo
        self._customer_repo = customer_repo
        self._shift_reconciliation_repo = shift_reconciliation_repo

    @require_permission(Permission.INVENTORY_VIEW.value)
    def get_fuel_type_summary(self, actor_user_id: str) -> List[FuelTypeSummary]:
        fuels = self._fuel_repo.list_active()
        tanks = self._tank_repo.list_all()
        nozzles = self._nozzle_repo.list_all()

        summaries = []
        for fuel in fuels:
            fuel_tanks = [t for t in tanks if t.fuel_id == fuel.id]
            fuel_nozzles = [n for n in nozzles if n.fuel_id == fuel.id]

            summary = FuelTypeSummary(
                fuel_type=fuel.fuel_type,
                fuel_id=fuel.id,
                tank_count=len(fuel_tanks),
                total_capacity=sum((t.capacity for t in fuel_tanks), Decimal("0")),
                total_current_stock=sum((t.current_stock for t in fuel_tanks), Decimal("0")),
                nozzle_count=len(fuel_nozzles),
                active_nozzle_count=len([n for n in fuel_nozzles if n.status == "active"]),
            )

            latest_variances = []
            for tank in fuel_tanks:
                latest = self._reconciliation_repo.get_latest_for_tank(tank.id)
                if latest:
                    latest_variances.append(latest)
            if latest_variances:
                worst = max(latest_variances, key=lambda r: abs(r.variance_percent))
                summary.latest_variance_percent = worst.variance_percent
                summary.latest_variance_classification = worst.classification

            summaries.append(summary)

        return summaries

    @require_permission(Permission.SALE_VIEW.value)
    def get_sales_report(self, actor_user_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None) -> TableReport:
        start_utc, end_utc = self._date_bounds(date_from, date_to)
        sales = [
            s
            for s in self._sale_repo.list_all()
            if s.status == SaleStatus.COMPLETED.value and _in_range(s.sale_at, start_utc, end_utc)
        ]

        rows = []
        by_fuel: dict[str, list] = {}
        for sale in sales:
            fuel_type = sale.fuel.fuel_type if sale.fuel else "Unknown"
            by_fuel.setdefault(fuel_type, []).append(sale)

        for fuel_type, fuel_sales in sorted(by_fuel.items()):
            quantity = sum((s.quantity for s in fuel_sales), Decimal("0"))
            amount = sum((s.amount for s in fuel_sales), Decimal("0"))
            rows.append([fuel_type, str(len(fuel_sales)), f"{quantity:.2f}", f"{amount:.2f}"])

        total_quantity = sum((s.quantity for s in sales), Decimal("0"))
        total_amount = sum((s.amount for s in sales), Decimal("0"))
        rows.append(["Total", str(len(sales)), f"{total_quantity:.2f}", f"{total_amount:.2f}"])

        return TableReport(title="Sales Report", headers=["Fuel Type", "Sales", "Quantity (L)", "Amount"], rows=rows)

    @require_permission(Permission.SALE_VIEW.value)
    def get_payment_summary_report(self, actor_user_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None) -> TableReport:
        start_utc, end_utc = self._date_bounds(date_from, date_to)
        payments = [p for p in self._payment_repo.list_all() if _in_range(p.payment_at, start_utc, end_utc)]

        rows = []
        for method in PaymentMethod:
            method_payments = [p for p in payments if p.method == method.value]
            if not method_payments:
                continue
            totals = {status: Decimal("0") for status in PaymentStatus}
            for payment in method_payments:
                totals[PaymentStatus(payment.status)] += payment.amount
            rows.append(
                [
                    method.value.title(),
                    str(len(method_payments)),
                    f"{totals[PaymentStatus.SUCCESS]:.2f}",
                    f"{totals[PaymentStatus.PENDING]:.2f}",
                    f"{totals[PaymentStatus.FAILED]:.2f}",
                    f"{totals[PaymentStatus.REVERSED]:.2f}",
                    f"{totals[PaymentStatus.REFUNDED]:.2f}",
                ]
            )

        return TableReport(
            title="Payment Summary Report",
            headers=["Method", "Count", "Success", "Pending", "Failed", "Reversed", "Refunded"],
            rows=rows,
        )

    @require_permission(Permission.EXPENSE_VIEW.value)
    def get_expense_summary_report(self, actor_user_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None) -> TableReport:
        expenses = [
            e
            for e in self._expense_repo.list_all()
            if (date_from is None or e.expense_date >= date_from) and (date_to is None or e.expense_date <= date_to)
        ]

        rows = []
        by_category: dict[str, list] = {}
        for expense in expenses:
            category_name = expense.category.name if expense.category else "Unknown"
            by_category.setdefault(category_name, []).append(expense)

        for category_name, category_expenses in sorted(by_category.items()):
            approved = sum((e.amount for e in category_expenses if e.status == "approved"), Decimal("0"))
            pending = sum((e.amount for e in category_expenses if e.status == "pending"), Decimal("0"))
            rejected = sum((e.amount for e in category_expenses if e.status == "rejected"), Decimal("0"))
            rows.append([category_name, str(len(category_expenses)), f"{approved:.2f}", f"{pending:.2f}", f"{rejected:.2f}"])

        return TableReport(
            title="Expense Summary Report",
            headers=["Category", "Count", "Approved", "Pending", "Rejected"],
            rows=rows,
        )

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def get_reconciliation_report(self, actor_user_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None) -> TableReport:
        start_utc, end_utc = self._date_bounds(date_from, date_to)
        reconciliations = [
            r for r in self._shift_reconciliation_repo.list_all() if _in_range(r.performed_at, start_utc, end_utc)
        ]

        rows = []
        for reconciliation in reconciliations:
            shift_label = f"{reconciliation.shift.shift_date} {reconciliation.shift.shift_label}" if reconciliation.shift else ""
            rows.append(
                [
                    shift_label,
                    f"{reconciliation.cash_variance:.2f}",
                    f"{reconciliation.upi_variance:.2f}",
                    f"{reconciliation.card_variance:.2f}",
                    reconciliation.classification.replace("_", " ").title(),
                    reconciliation.status.replace("_", " ").title(),
                ]
            )

        return TableReport(
            title="Shift Reconciliation Report",
            headers=["Shift", "Cash Var.", "UPI Var.", "Card Var.", "Classification", "Status"],
            rows=rows,
        )

    @require_permission(Permission.CREDIT_VIEW.value)
    def get_credit_fuel_type_report(self, actor_user_id: str) -> TableReport:
        """Fuel-type-sectioned credit report (explicit user requirement,
        2026-08-16). "Extended" is directly attributable to a fuel type via
        each credit sale's own nozzle->fuel link. "Collected" and
        "Outstanding" are only reported at the overall portfolio level, not
        per fuel type - CustomerPayment is recorded against a customer's
        whole balance, not allocated to individual sales, so a per-fuel
        "collected" figure would have to be invented rather than derived;
        this report is honest about what the underlying data actually
        supports instead of fabricating a number."""

        credit_sales = [s for s in self._sale_repo.list_all() if s.payment_method == PaymentMethod.CREDIT.value and s.status == SaleStatus.COMPLETED.value]

        rows = []
        by_fuel: dict[str, list] = {}
        for sale in credit_sales:
            fuel_type = sale.fuel.fuel_type if sale.fuel else "Unknown"
            by_fuel.setdefault(fuel_type, []).append(sale)

        for fuel_type, fuel_sales in sorted(by_fuel.items()):
            extended = sum((s.amount for s in fuel_sales), Decimal("0"))
            rows.append([fuel_type, str(len(fuel_sales)), f"{extended:.2f}"])

        total_extended = sum((s.amount for s in credit_sales), Decimal("0"))
        total_collected = sum((p.amount for p in self._customer_payment_repo.list_all()), Decimal("0"))
        rows.append(["Overall", str(len(credit_sales)), f"{total_extended:.2f}"])
        rows.append(["  Total collected (all fuel types)", "", f"{total_collected:.2f}"])
        rows.append(["  Total outstanding (all fuel types)", "", f"{total_extended - total_collected:.2f}"])

        return TableReport(title="Credit Report by Fuel Type", headers=["Fuel Type", "Credit Sales", "Extended"], rows=rows)

    @require_permission(Permission.CREDIT_VIEW.value)
    def get_customer_outstanding_report(self, actor_user_id: str) -> TableReport:
        rows = []
        for account in self._credit_account_repo.list_all():
            credit_sales_total = sum(
                (
                    s.amount
                    for s in self._sale_repo.list_by_customer(account.customer_id)
                    if s.payment_method == PaymentMethod.CREDIT.value and s.status == SaleStatus.COMPLETED.value
                ),
                Decimal("0"),
            )
            payments_total = sum(
                (p.amount for p in self._customer_payment_repo.list_for_customer(account.customer_id)), Decimal("0")
            )
            outstanding = credit_sales_total - payments_total
            customer_name = account.customer.name if account.customer else ""
            rows.append([customer_name, f"{account.credit_limit:.2f}", f"{outstanding:.2f}"])

        return TableReport(title="Customer Outstanding Report", headers=["Customer", "Credit Limit", "Outstanding"], rows=rows)

    @staticmethod
    def _date_bounds(date_from: Optional[date], date_to: Optional[date]):
        start_utc = local_day_bounds_utc(date_from)[0] if date_from else None
        end_utc = local_day_bounds_utc(date_to)[1] if date_to else None
        return start_utc, end_utc
