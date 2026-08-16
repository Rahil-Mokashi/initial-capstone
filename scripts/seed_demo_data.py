"""Demo data seeder (user-requested 2026-08-16: "feed the app with some
data... so I can see how it's actually working - reports and
everything - and later we can clean it off").

Not for production. Generates ~10 weeks of plausible business history
(shifts, sales, purchases, expenses, credit customers, reconciliations)
so every report and the Business Insights forecast have something real
to show. Master-data setup (employees, tanks, nozzles, suppliers) goes
through the real service layer for proper audit logging; the bulk
historical records (shifts, sales, purchase orders, expenses) are
inserted directly, since going through hundreds of individual
permission-checked service calls that each stamp "now" would be slow
and most of those services don't accept a backdated timestamp anyway.

Idempotent-ish: running it twice is harmless but will duplicate the
historical data (each run creates a fresh 10-week history ending
today). To start clean, delete the database file and re-run
`python -m app.main` (or this script) - the standard "reset a SQLite
dev database" move, no separate wipe command needed for a throwaway
demo dataset.

Usage:
    python scripts/seed_demo_data.py
    PETROL_PUMP_DB_PATH=... python scripts/seed_demo_data.py   # target a specific DB file
"""

import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.constants import (  # noqa: E402
    AssignmentStatus,
    ExpenseStatus,
    PaymentMethod,
    PaymentStatus,
    PurchaseOrderStatus,
    ReconciliationStatus,
    SaleStatus,
    ShiftStatus,
    UserRole,
    VarianceClassification,
)
from app.core.security import hash_password  # noqa: E402
from app.database.connection import SessionLocal, init_db  # noqa: E402
from app.database.seed import seed_initial_data  # noqa: E402
from app.models.credit_account import CreditAccount  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.customer_payment import CustomerPayment  # noqa: E402
from app.models.dispenser import Dispenser  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.expense import Expense, ExpenseCategory  # noqa: E402
from app.models.fuel import Fuel  # noqa: E402
from app.models.nozzle import Nozzle  # noqa: E402
from app.models.nozzle_assignment import NozzleAssignment  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.sale import Sale  # noqa: E402
from app.models.shift import Shift  # noqa: E402
from app.models.shift_reconciliation import ShiftReconciliation  # noqa: E402
from app.models.supplier import Supplier  # noqa: E402
from app.models.tank import Tank  # noqa: E402
from app.models.user import User  # noqa: E402

DAYS_OF_HISTORY = 70

FUEL_RATES = {"Petrol": Decimal("102.50"), "Diesel": Decimal("94.20"), "Power": Decimal("110.00")}
FUEL_BASE_COST = {"Petrol": Decimal("95.00"), "Diesel": Decimal("87.00"), "Power": Decimal("101.00")}
TANK_CAPACITY = {"Petrol": Decimal("20000"), "Diesel": Decimal("20000"), "Power": Decimal("10000")}

random.seed(20260816)


def _utc(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=timezone.utc)


def main() -> None:
    init_db()
    seed_initial_data()

    session = SessionLocal()
    try:
        admin = session.query(User).filter_by(username="admin").first()
        roles = {r.name: r for r in session.query(Role).all()}

        if session.query(Supplier).filter_by(name="Regional Fuel Distributors").first():
            print("Demo data already looks present (found the demo supplier) - seeding another batch of history anyway.")

        fuels = {f.fuel_type: f for f in session.query(Fuel).all()}
        for fuel_type, fuel in fuels.items():
            fuel.rate_per_liter = FUEL_RATES.get(fuel_type, fuel.rate_per_liter)
        session.commit()

        employees, attendant_ids = _seed_employees_and_users(session, roles)
        tanks = _seed_tanks(session, fuels)
        nozzles = _seed_dispensers_and_nozzles(session, fuels, tanks)
        _seed_purchase_history(session, admin, fuels)
        customers = _seed_customers_and_credit(session, admin)
        shifts = _seed_shifts_and_sales(session, admin, employees, attendant_ids, nozzles, fuels, tanks, customers)
        _seed_expenses(session, admin, employees)
        _seed_reconciliations(session, admin, shifts)

        session.commit()
        print(f"Seeded {DAYS_OF_HISTORY} days of demo data. Log in as one of:")
        print("  admin / Admin@123 (must change password on first login)")
        for username, role_name in [("manager1", "Manager"), ("accountant1", "Accountant"), ("supervisor1", "Shift Supervisor"), ("attendant1", "Attendant")]:
            print(f"  {username} / Passw0rd!  ({role_name})")
    finally:
        session.close()


def _seed_employees_and_users(session, roles):
    employee_specs = [
        ("EMP-1001", "Anita", "Sharma", UserRole.MANAGER, "manager1"),
        ("EMP-1002", "Vikram", "Rao", UserRole.ACCOUNTANT, "accountant1"),
        ("EMP-1003", "Sunita", "Iyer", UserRole.SHIFT_SUPERVISOR, "supervisor1"),
        ("EMP-1004", "Ravi", "Kumar", UserRole.ATTENDANT, "attendant1"),
        ("EMP-1005", "Deepak", "Singh", UserRole.ATTENDANT, "attendant2"),
        ("EMP-1006", "Meena", "Patel", UserRole.ATTENDANT, None),
    ]

    employees = {}
    attendant_ids = []
    for code, first, last, role, username in employee_specs:
        existing = session.query(Employee).filter_by(employee_code=code).first()
        if existing:
            employees[code] = existing
            if role == UserRole.ATTENDANT:
                attendant_ids.append(existing.id)
            continue

        user = None
        if username:
            user = User(
                username=username, email=f"{username}@example.com",
                password_hash=hash_password("Passw0rd!"), role=roles[role.value], is_active=True,
            )
            session.add(user)
            session.commit()

        employee = Employee(
            employee_code=code, first_name=first, last_name=last,
            contact_number=f"98765{random.randint(10000, 99999)}",
            joining_date=date.today() - timedelta(days=random.randint(120, 900)),
            designation=role.value.replace("_", " ").title(),
            user_id=user.id if user else None,
        )
        session.add(employee)
        session.commit()
        employees[code] = employee
        if role == UserRole.ATTENDANT:
            attendant_ids.append(employee.id)

    return employees, attendant_ids


def _seed_tanks(session, fuels):
    tanks = {}
    for fuel_type, fuel in fuels.items():
        code = f"TANK-{fuel_type.upper()[:3]}"
        existing = session.query(Tank).filter_by(code=code).first()
        if existing:
            tanks[fuel_type] = existing
            continue
        capacity = TANK_CAPACITY.get(fuel_type, Decimal("15000"))
        tank = Tank(
            code=code, fuel_id=fuel.id, capacity=capacity,
            current_stock=capacity * Decimal("0.65"), opening_stock=capacity * Decimal("0.65"),
            status="active",
        )
        session.add(tank)
        session.commit()
        tanks[fuel_type] = tank
    return tanks


def _seed_dispensers_and_nozzles(session, fuels, tanks):
    layout = [
        ("D1", [("N1", "Petrol"), ("N2", "Diesel")]),
        ("D2", [("N3", "Petrol"), ("N4", "Diesel")]),
        ("D3", [("N5", "Power"), ("N6", "Petrol")]),
    ]
    nozzles_by_fuel: dict = {"Petrol": [], "Diesel": [], "Power": []}
    for dispenser_code, nozzle_specs in layout:
        dispenser = session.query(Dispenser).filter_by(code=dispenser_code).first()
        if not dispenser:
            dispenser = Dispenser(code=dispenser_code, status="active")
            session.add(dispenser)
            session.commit()
        for nozzle_code, fuel_type in nozzle_specs:
            nozzle = session.query(Nozzle).filter_by(code=nozzle_code).first()
            if not nozzle:
                nozzle = Nozzle(
                    code=nozzle_code, dispenser_id=dispenser.id, fuel_id=fuels[fuel_type].id,
                    tank_id=tanks[fuel_type].id, status="active",
                )
                session.add(nozzle)
                session.commit()
            nozzles_by_fuel[fuel_type].append(nozzle)
    return nozzles_by_fuel


def _seed_purchase_history(session, admin, fuels):
    supplier = session.query(Supplier).filter_by(name="Regional Fuel Distributors").first()
    if not supplier:
        supplier = Supplier(name="Regional Fuel Distributors", phone="9812345670", contact_person="S. Menon", status="active")
        session.add(supplier)
        session.commit()

    order_dates = [date.today() - timedelta(days=offset) for offset in range(DAYS_OF_HISTORY, -1, -14)]
    for index, order_date in enumerate(order_dates):
        po = PurchaseOrder(
            po_number=f"DEMO-PO-{order_date.isoformat()}", supplier_id=supplier.id, created_by_id=admin.id,
            status=PurchaseOrderStatus.DELIVERED.value, order_date=order_date,
        )
        session.add(po)
        session.commit()

        drift = Decimal(str(index)) * Decimal("0.35")  # fuel cost drifts up slightly over the period
        for fuel_type, fuel in fuels.items():
            rate = FUEL_BASE_COST.get(fuel_type, Decimal("90.00")) + drift
            item = PurchaseOrderItem(
                purchase_order_id=po.id, fuel_id=fuel.id,
                quantity_ordered=Decimal(random.randint(4000, 9000)), rate_per_liter=rate,
            )
            session.add(item)
        session.commit()


def _seed_customers_and_credit(session, admin):
    customer_specs = [
        ("Ravi Transports", Decimal("15000")),
        ("Sunrise Logistics", Decimal("25000")),
        ("Metro Cabs Cooperative", Decimal("10000")),
    ]
    customers = []
    for name, limit in customer_specs:
        customer = session.query(Customer).filter_by(name=name).first()
        if not customer:
            customer = Customer(name=name, phone=f"98765{random.randint(10000, 99999)}", status="active")
            session.add(customer)
            session.commit()
        customers.append(customer)

        if not session.query(CreditAccount).filter_by(customer_id=customer.id).first():
            account = CreditAccount(customer_id=customer.id, credit_limit=limit, payment_due_days=30, created_by_id=admin.id)
            session.add(account)
            session.commit()
    return customers


def _seed_shifts_and_sales(session, admin, employees, attendant_ids, nozzles, fuels, tanks, customers):
    shifts = []
    total_sold = {fuel_type: Decimal("0") for fuel_type in fuels}

    for day_offset in range(DAYS_OF_HISTORY, -1, -1):
        shift_date = date.today() - timedelta(days=day_offset)
        is_today = day_offset == 0

        shift = Shift(
            shift_date=shift_date, shift_label="Morning", opened_by_id=admin.id,
            status=ShiftStatus.OPEN.value if is_today else ShiftStatus.CLOSED.value,
        )
        session.add(shift)
        session.commit()
        shifts.append(shift)

        assigned_attendants = random.sample(attendant_ids, k=min(2, len(attendant_ids)))
        assignment_nozzles = random.sample(
            [n for group in nozzles.values() for n in group], k=min(2, sum(len(g) for g in nozzles.values()))
        )
        for attendant_id, nozzle in zip(assigned_attendants, assignment_nozzles):
            assignment = NozzleAssignment(
                employee_id=attendant_id, nozzle_id=nozzle.id, shift_id=shift.id,
                opening_meter=Decimal(random.randint(1000, 5000)), assigned_by_id=admin.id,
                status=AssignmentStatus.ACTIVE.value if is_today else AssignmentStatus.COMPLETED.value,
            )
            if not is_today:
                assignment.closing_meter = assignment.opening_meter + Decimal(random.randint(50, 300))
            session.add(assignment)
        session.commit()

        # Progress through the window (0.0 -> 1.0) so Petrol trends up
        # and Diesel stays roughly flat/noisy - gives the sales forecast
        # something real to classify differently per fuel.
        progress = 1 - (day_offset / DAYS_OF_HISTORY)
        sale_count = random.randint(4, 9)
        for _ in range(sale_count):
            fuel_type = random.choices(["Petrol", "Diesel", "Power"], weights=[0.55, 0.35, 0.10])[0]
            fuel = fuels[fuel_type]
            nozzle = random.choice(nozzles[fuel_type])
            employee_id = random.choice(attendant_ids)

            if fuel_type == "Petrol":
                base_quantity = 18 + progress * 14  # gentle upward trend
            elif fuel_type == "Diesel":
                base_quantity = 22 + random.uniform(-4, 4)  # flat, noisy
            else:
                base_quantity = 10 + random.uniform(-2, 2)
            quantity = Decimal(str(round(max(2.0, base_quantity + random.uniform(-3, 3)), 2)))

            payment_method = random.choices(
                [PaymentMethod.CASH, PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.CREDIT],
                weights=[0.55, 0.25, 0.12, 0.08],
            )[0]
            customer = random.choice(customers) if payment_method == PaymentMethod.CREDIT else None

            rate = fuel.rate_per_liter
            amount = (quantity * rate).quantize(Decimal("0.01"))
            sale_time = _utc(shift_date, random.randint(7, 13), random.randint(0, 59))

            sale = Sale(
                receipt_number=f"DEMO-{shift_date.isoformat()}-{random.randint(1000, 9999)}",
                sale_at=sale_time, shift_id=shift.id, nozzle_id=nozzle.id, fuel_id=fuel.id,
                employee_id=employee_id, quantity=quantity, rate_per_liter=rate, amount=amount,
                payment_method=payment_method.value, customer_id=customer.id if customer else None,
                status=SaleStatus.COMPLETED.value, recorded_by_id=admin.id,
            )
            session.add(sale)
            session.commit()

            payment_status = PaymentStatus.PENDING if payment_method == PaymentMethod.CREDIT else PaymentStatus.SUCCESS
            payment = Payment(
                sale_id=sale.id, amount=amount, method=payment_method.value, status=payment_status.value,
                payment_at=sale_time, shift_id=shift.id, attendant_id=employee_id, recorded_by_id=admin.id,
            )
            session.add(payment)

            total_sold[fuel_type] += quantity

        session.commit()

    for fuel_type, tank in tanks.items():
        tank.current_stock = max(Decimal("0"), tank.current_stock - total_sold[fuel_type])
    session.commit()

    # A couple of partial payments against the credit customers so
    # get_customer_outstanding_report/get_credit_fuel_type_report show
    # some collected amount, not just an ever-growing balance.
    for customer in customers:
        credit_sales_total = sum(
            (s.amount for s in session.query(Sale).filter_by(customer_id=customer.id, payment_method=PaymentMethod.CREDIT.value)),
            Decimal("0"),
        )
        if credit_sales_total > 0:
            payment = CustomerPayment(
                customer_id=customer.id, amount=(credit_sales_total * Decimal("0.4")).quantize(Decimal("0.01")),
                payment_date=date.today() - timedelta(days=random.randint(1, 10)),
                payment_method=PaymentMethod.UPI.value, recorded_by_id=admin.id,
            )
            session.add(payment)
    session.commit()

    return shifts


def _seed_expenses(session, admin, employees):
    category_names = ["Electricity", "Maintenance", "Cleaning Supplies", "Staff Welfare"]
    categories = []
    for name in category_names:
        category = session.query(ExpenseCategory).filter_by(name=name).first()
        if not category:
            category = ExpenseCategory(name=name, status="active")
            session.add(category)
            session.commit()
        categories.append(category)

    employee_ids = [e.id for e in employees.values()]
    for day_offset in range(DAYS_OF_HISTORY, -1, -5):
        expense_date = date.today() - timedelta(days=day_offset)
        category = random.choice(categories)
        status = random.choices(
            [ExpenseStatus.APPROVED, ExpenseStatus.PENDING, ExpenseStatus.REJECTED], weights=[0.75, 0.15, 0.10]
        )[0]
        expense = Expense(
            category_id=category.id, amount=Decimal(random.randint(300, 4000)),
            expense_date=expense_date, payment_method=PaymentMethod.CASH.value,
            employee_id=random.choice(employee_ids), status=status.value, recorded_by_id=admin.id,
        )
        if status == ExpenseStatus.APPROVED:
            expense.approved_by_id = admin.id
            expense.approved_at = _utc(expense_date, 18)
        elif status == ExpenseStatus.REJECTED:
            expense.approved_by_id = admin.id
            expense.approval_remarks = "Missing receipt"
        session.add(expense)
    session.commit()


def _seed_reconciliations(session, admin, shifts):
    closed_shifts = [s for s in shifts if s.status == ShiftStatus.CLOSED.value][-10:]
    for shift in closed_shifts:
        if session.query(ShiftReconciliation).filter_by(shift_id=shift.id).first():
            continue

        sales = session.query(Sale).filter_by(shift_id=shift.id, status=SaleStatus.COMPLETED.value).all()
        expected_cash = sum((s.amount for s in sales if s.payment_method == PaymentMethod.CASH.value), Decimal("0"))
        expected_upi = sum((s.amount for s in sales if s.payment_method == PaymentMethod.UPI.value), Decimal("0"))
        expected_card = sum((s.amount for s in sales if s.payment_method == PaymentMethod.CARD.value), Decimal("0"))

        # Small realistic variance most of the time, occasionally a
        # bigger one so the reconciliation report shows a mix of
        # classifications, not uniformly "normal".
        variance_factor = Decimal(str(round(random.uniform(-0.03, 0.03), 4)))
        declared_cash = (expected_cash * (1 + variance_factor)).quantize(Decimal("0.01"))

        cash_variance = declared_cash - expected_cash
        classification = VarianceClassification.NORMAL
        if expected_cash > 0:
            variance_percent = abs(cash_variance / expected_cash * 100)
            if variance_percent > 2:
                classification = VarianceClassification.APPROVAL_REQUIRED
            elif variance_percent > 1:
                classification = VarianceClassification.INVESTIGATION_REQUIRED
            elif variance_percent > 0.5:
                classification = VarianceClassification.WARNING

        status = (
            ReconciliationStatus.ACCEPTED
            if classification in (VarianceClassification.NORMAL, VarianceClassification.WARNING)
            else ReconciliationStatus.PENDING_APPROVAL
        )

        reconciliation = ShiftReconciliation(
            shift_id=shift.id, expected_cash=expected_cash, declared_cash=declared_cash, cash_variance=cash_variance,
            expected_upi=expected_upi, declared_upi=expected_upi, upi_variance=Decimal("0"),
            expected_card=expected_card, declared_card=expected_card, card_variance=Decimal("0"),
            classification=classification.value, status=status.value, performed_by_id=admin.id,
        )
        session.add(reconciliation)
    session.commit()


if __name__ == "__main__":
    main()
