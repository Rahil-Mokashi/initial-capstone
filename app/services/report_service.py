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

from app.core.constants import (
    AttendanceStatus,
    ExpenseStatus,
    PaymentMethod,
    PaymentStatus,
    Permission,
    SaleStatus,
    TankTransactionType,
)
from app.core.dates import local_date_of, local_day_bounds_utc
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


def _sum_by_type(movements, transaction_type: str) -> Decimal:
    """Total the signed quantities of one kind of tank movement.

    A module-level function rather than a closure defined inside the
    per-tank loop: closing over the loop variable is the classic
    late-binding trap, and it is only safe here because the result
    happens to be consumed in the same iteration. Not worth leaving as a
    pattern for the next person to copy.
    """
    return sum((m.quantity for m in movements if m.transaction_type == transaction_type), Decimal("0"))


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
        # Added for the problemstatement.md #25-32 pass (daily, attendant/
        # nozzle, fuel movement, cash book, attendance). Required rather
        # than defaulted to None, like every other dependency here: a
        # report that silently omits a section because a repository was
        # never wired in is worse than one that fails at construction,
        # since nobody reading the output can tell the difference between
        # "no data" and "never asked".
        tank_transaction_repo,
        attendance_repo,
        employee_repo,
        shift_repo,
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
        self._tank_transaction_repo = tank_transaction_repo
        self._attendance_repo = attendance_repo
        self._employee_repo = employee_repo
        self._shift_repo = shift_repo

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

    # ------------------------------------------------------------------
    # problemstatement.md #25-32: daily, attendant/nozzle, inventory
    # movement, financial ledger and HR reports.
    #
    # Every one of these groups by the LOCAL business day via
    # local_date_of(), never `.date()` on a stored timestamp. That
    # distinction has already produced three separate shipped bugs in
    # this project (fuel reconciliation boundaries, credit overdue
    # flagging, customer statements): stored datetimes are UTC instants,
    # so on IST a sale at 02:00 local belongs to the previous UTC day and
    # a report grouped by `.date()` files it under the wrong trading day.
    # ------------------------------------------------------------------

    @require_permission(Permission.SALE_VIEW.value)
    def get_daily_summary_report(
        self, actor_user_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> TableReport:
        """One row per trading day: what was sold, how it was paid for,
        what went out, and what is left.

        This is the report a pump owner opens first thing, which is why
        it puts the payment-method split on the same line as the totals -
        the question is never just "how much did we take" but "how much
        of it is cash I should be able to count".
        """
        start_utc, end_utc = self._date_bounds(date_from, date_to)

        sales = [
            s
            for s in self._sale_repo.list_all()
            if s.status == SaleStatus.COMPLETED.value and _in_range(s.sale_at, start_utc, end_utc)
        ]
        expenses = [
            e
            for e in self._expense_repo.list_all()
            if e.status == ExpenseStatus.APPROVED.value
            and (date_from is None or e.expense_date >= date_from)
            and (date_to is None or e.expense_date <= date_to)
        ]

        days: dict[date, dict] = {}

        def bucket(day: date) -> dict:
            return days.setdefault(
                day,
                {
                    "count": 0,
                    "quantity": Decimal("0"),
                    "methods": {m.value: Decimal("0") for m in PaymentMethod},
                    "expenses": Decimal("0"),
                },
            )

        for sale in sales:
            entry = bucket(local_date_of(sale.sale_at))
            entry["count"] += 1
            entry["quantity"] += sale.quantity
            entry["methods"][sale.payment_method] = entry["methods"].get(sale.payment_method, Decimal("0")) + sale.amount

        for expense in expenses:
            bucket(expense.expense_date)["expenses"] += expense.amount

        rows = []
        totals = {
            "count": 0,
            "quantity": Decimal("0"),
            "methods": {m.value: Decimal("0") for m in PaymentMethod},
            "expenses": Decimal("0"),
        }
        for day in sorted(days):
            entry = days[day]
            gross = sum(entry["methods"].values(), Decimal("0"))
            rows.append(
                [
                    day.isoformat(),
                    str(entry["count"]),
                    f"{entry['quantity']:.2f}",
                    f"{entry['methods'].get(PaymentMethod.CASH.value, Decimal('0')):.2f}",
                    f"{entry['methods'].get(PaymentMethod.UPI.value, Decimal('0')):.2f}",
                    f"{entry['methods'].get(PaymentMethod.CARD.value, Decimal('0')):.2f}",
                    f"{entry['methods'].get(PaymentMethod.CREDIT.value, Decimal('0')):.2f}",
                    f"{gross:.2f}",
                    f"{entry['expenses']:.2f}",
                    f"{gross - entry['expenses']:.2f}",
                ]
            )
            totals["count"] += entry["count"]
            totals["quantity"] += entry["quantity"]
            totals["expenses"] += entry["expenses"]
            for method, amount in entry["methods"].items():
                totals["methods"][method] = totals["methods"].get(method, Decimal("0")) + amount

        if rows:
            gross_total = sum(totals["methods"].values(), Decimal("0"))
            rows.append(
                [
                    "Total",
                    str(totals["count"]),
                    f"{totals['quantity']:.2f}",
                    f"{totals['methods'][PaymentMethod.CASH.value]:.2f}",
                    f"{totals['methods'][PaymentMethod.UPI.value]:.2f}",
                    f"{totals['methods'][PaymentMethod.CARD.value]:.2f}",
                    f"{totals['methods'][PaymentMethod.CREDIT.value]:.2f}",
                    f"{gross_total:.2f}",
                    f"{totals['expenses']:.2f}",
                    f"{gross_total - totals['expenses']:.2f}",
                ]
            )

        return TableReport(
            title="Daily Summary Report",
            headers=["Date", "Sales", "Qty (L)", "Cash", "UPI", "Card", "Credit", "Gross", "Expenses", "Net"],
            rows=rows,
        )

    @require_permission(Permission.SALE_VIEW.value)
    def get_attendant_nozzle_report(
        self,
        actor_user_id: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        employee_id: Optional[str] = None,
        nozzle_id: Optional[str] = None,
    ) -> TableReport:
        """Sales broken down by who dispensed them and from which nozzle
        (problemstatement.md #26's attendant-wise/nozzle-wise breakdown).

        Closes the "filter by employee/nozzle" item too, since this is
        the report where those dimensions actually mean something.

        Deliberately reports quantity and value only. It is a record of
        what happened at a nozzle, not a ranking of staff: the figures
        depend on shift length, which nozzle somebody was assigned and
        how busy the forecourt was, so presenting them as performance
        would invite exactly the wrong conclusion - the same
        non-accusatory principle already applied to variance.
        """
        start_utc, end_utc = self._date_bounds(date_from, date_to)

        sales = [
            s
            for s in self._sale_repo.list_all()
            if s.status == SaleStatus.COMPLETED.value
            and _in_range(s.sale_at, start_utc, end_utc)
            and (employee_id is None or s.employee_id == employee_id)
            and (nozzle_id is None or s.nozzle_id == nozzle_id)
        ]

        grouped: dict[tuple, dict] = {}
        for sale in sales:
            employee = sale.employee
            nozzle = sale.nozzle
            key = (
                f"{employee.first_name} {employee.last_name}" if employee else "Unknown",
                nozzle.code if nozzle else "Unknown",
                sale.fuel.fuel_type if sale.fuel else "Unknown",
            )
            entry = grouped.setdefault(key, {"count": 0, "quantity": Decimal("0"), "amount": Decimal("0")})
            entry["count"] += 1
            entry["quantity"] += sale.quantity
            entry["amount"] += sale.amount

        rows = [
            [name, nozzle_code, fuel_type, str(entry["count"]), f"{entry['quantity']:.2f}", f"{entry['amount']:.2f}"]
            for (name, nozzle_code, fuel_type), entry in sorted(grouped.items())
        ]

        if rows:
            rows.append(
                [
                    "Total",
                    "",
                    "",
                    str(len(sales)),
                    f"{sum((s.quantity for s in sales), Decimal('0')):.2f}",
                    f"{sum((s.amount for s in sales), Decimal('0')):.2f}",
                ]
            )

        return TableReport(
            title="Attendant & Nozzle Report",
            headers=["Attendant", "Nozzle", "Fuel", "Sales", "Quantity (L)", "Amount"],
            rows=rows,
        )

    @require_permission(Permission.INVENTORY_VIEW.value)
    def get_fuel_movement_report(
        self, actor_user_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> TableReport:
        """Every litre into and out of each tank over a period
        (problemstatement.md #29's inventory movement report).

        Receipts, issues and adjustments are shown separately rather than
        netted, because they answer different questions: a large net
        change is normal trading, while a large ADJUSTMENT figure is the
        one that warrants a conversation. Issue and adjustment quantities
        are stored as signed deltas, so they are reported with their sign
        intact instead of being made to look positive.
        """
        start_utc, end_utc = self._date_bounds(date_from, date_to)

        rows = []
        for tank in sorted(self._tank_repo.list_all(), key=lambda t: t.code):
            movements = [
                t for t in self._tank_transaction_repo.list_for_tank(tank.id) if _in_range(t.transaction_at, start_utc, end_utc)
            ]
            if not movements:
                continue

            receipts = _sum_by_type(movements, TankTransactionType.RECEIPT.value)
            issues = _sum_by_type(movements, TankTransactionType.ISSUE.value)
            adjustments = _sum_by_type(movements, TankTransactionType.ADJUSTMENT.value)

            rows.append(
                [
                    tank.code,
                    tank.fuel.fuel_type if tank.fuel else "Unknown",
                    str(len(movements)),
                    f"{receipts:.3f}",
                    f"{issues:.3f}",
                    f"{adjustments:.3f}",
                    f"{receipts + issues + adjustments:.3f}",
                    f"{tank.current_stock:.3f}",
                ]
            )

        return TableReport(
            title="Fuel Movement Report",
            headers=["Tank", "Fuel", "Movements", "Receipts (L)", "Issues (L)", "Adjustments (L)", "Net (L)", "Stock Now (L)"],
            rows=rows,
        )

    @require_permission(Permission.EXPENSE_VIEW.value)
    def get_cash_book_report(
        self, actor_user_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> TableReport:
        """Money in and money out per day, with a running balance
        (problemstatement.md #30's cash book / ledger).

        Gated on EXPENSE_VIEW rather than SALE_VIEW on purpose. The
        report combines takings with expenditure, and EXPENSE_VIEW is the
        stricter of the two grants - it is withheld from Shift Supervisor
        and Attendant. Reporting must not become a side door to data a
        role cannot open directly, so a combined report takes the
        stricter permission of everything it discloses.

        Money in counts completed sales settled by cash, UPI or card plus
        payments received from credit customers. A CREDIT sale is
        deliberately excluded on the day it happens - no money arrived -
        and appears later as a customer payment, which is what makes this
        a cash book rather than a restatement of the sales report.
        """
        start_utc, end_utc = self._date_bounds(date_from, date_to)

        def within(day: date) -> bool:
            return (date_from is None or day >= date_from) and (date_to is None or day <= date_to)

        days: dict[date, dict] = {}

        def bucket(day: date) -> dict:
            return days.setdefault(day, {"in": Decimal("0"), "out": Decimal("0")})

        for sale in self._sale_repo.list_all():
            if sale.status != SaleStatus.COMPLETED.value or not _in_range(sale.sale_at, start_utc, end_utc):
                continue
            if sale.payment_method == PaymentMethod.CREDIT.value:
                continue
            bucket(local_date_of(sale.sale_at))["in"] += sale.amount

        for payment in self._customer_payment_repo.list_all():
            if within(payment.payment_date):
                bucket(payment.payment_date)["in"] += payment.amount

        for expense in self._expense_repo.list_all():
            if expense.status == ExpenseStatus.APPROVED.value and within(expense.expense_date):
                bucket(expense.expense_date)["out"] += expense.amount

        rows = []
        running = Decimal("0")
        total_in = Decimal("0")
        total_out = Decimal("0")
        for day in sorted(days):
            entry = days[day]
            running += entry["in"] - entry["out"]
            total_in += entry["in"]
            total_out += entry["out"]
            rows.append(
                [
                    day.isoformat(),
                    f"{entry['in']:.2f}",
                    f"{entry['out']:.2f}",
                    f"{entry['in'] - entry['out']:.2f}",
                    f"{running:.2f}",
                ]
            )

        if rows:
            rows.append(["Total", f"{total_in:.2f}", f"{total_out:.2f}", f"{total_in - total_out:.2f}", f"{running:.2f}"])

        return TableReport(
            title="Cash Book",
            headers=["Date", "Received", "Paid Out", "Net", "Running Balance"],
            rows=rows,
        )

    @require_permission(Permission.ATTENDANCE_VIEW.value)
    def get_attendance_report(
        self,
        actor_user_id: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        employee_id: Optional[str] = None,
    ) -> TableReport:
        """Attendance per employee over a period (problemstatement.md
        #28's HR reports).

        Counts each status separately rather than reducing the period to
        a single "days worked" figure: leave, half days and absence are
        different facts with different consequences for pay, and
        collapsing them would throw away exactly the detail the report
        exists to provide. Attendance dates are stored as real dates
        rather than timestamps, so no timezone conversion applies here.
        """
        employees = self._employee_repo.list_all()
        if employee_id is not None:
            employees = [e for e in employees if e.id == employee_id]

        rows = []
        for employee in sorted(employees, key=lambda e: e.employee_code):
            records = self._attendance_repo.list_for_employee(employee.id, date_from, date_to)
            if not records:
                continue
            counts = {status.value: 0 for status in AttendanceStatus}
            overtime = 0
            for record in records:
                counts[record.status] = counts.get(record.status, 0) + 1
                overtime += record.overtime_minutes or 0

            rows.append(
                [
                    employee.employee_code,
                    f"{employee.first_name} {employee.last_name}",
                    str(len(records)),
                    str(counts.get(AttendanceStatus.PRESENT.value, 0)),
                    str(counts.get(AttendanceStatus.ABSENT.value, 0)),
                    str(counts.get(AttendanceStatus.LATE.value, 0)),
                    str(counts.get(AttendanceStatus.HALF_DAY.value, 0)),
                    str(counts.get(AttendanceStatus.LEAVE.value, 0)),
                    f"{overtime / 60:.1f}",
                ]
            )

        return TableReport(
            title="Attendance Report",
            headers=["Code", "Employee", "Days", "Present", "Absent", "Late", "Half Day", "Leave", "Overtime (h)"],
            rows=rows,
        )

    def get_report_filter_options(self, actor_user_id: str) -> dict:
        """The employee and nozzle choices a report's filter drop-downs
        can offer this user.

        Deliberately undecorated, and each list is gated separately
        inside. Holding SALE_VIEW is what lets somebody open the
        attendant report, but it is not what entitles them to a roster of
        every employee's name - an Attendant has SALE_VIEW and no
        EMPLOYEE_VIEW. Returning a filter list they are not allowed to
        see would make a drop-down into a staff directory, so each list
        is gated on the permission that owns that data and simply comes
        back empty otherwise. Same shape as DashboardService.get_summary,
        which returns None for sections the actor cannot see.
        """
        options: dict[str, list] = {"employees": [], "nozzles": []}

        if self._auth_service.check_permission(actor_user_id, Permission.EMPLOYEE_VIEW.value):
            options["employees"] = [
                (f"{e.employee_code} - {e.first_name} {e.last_name}", e.id)
                for e in sorted(self._employee_repo.list_all(), key=lambda e: e.employee_code)
            ]

        if self._auth_service.check_permission(actor_user_id, Permission.NOZZLE_VIEW.value):
            options["nozzles"] = [
                (nozzle.code, nozzle.id) for nozzle in sorted(self._nozzle_repo.list_all(), key=lambda n: n.code)
            ]

        return options

    @staticmethod
    def _date_bounds(date_from: Optional[date], date_to: Optional[date]):
        start_utc = local_day_bounds_utc(date_from)[0] if date_from else None
        end_utc = local_day_bounds_utc(date_to)[1] if date_to else None
        return start_utc, end_utc
