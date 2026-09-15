import uuid
from datetime import datetime, timezone

from app import database as db_package
from app.core.constants import (
    CASH_SHORTAGE_EXPENSE_CATEGORY_NAME,
    DEFAULT_FUEL_TYPES,
    DEFAULT_TENDERS,
    PAYMENT_METHOD_TO_TENDER_NAME,
    ROLE_PERMISSIONS,
    Permission as PermissionName,
    UserRole,
)
from app.core.security import hash_password
from app.database.base import StatusEnum
from app.models.expense import Expense, ExpenseCategory
from app.models.fuel import Fuel
from app.models.payment import Payment
from app.models.permission import Permission
from app.models.role import Role
from app.models.sale import Sale
from app.models.tender import Tender
from app.models.user import User

DEFAULT_ADMIN_PASSWORD = "Admin@123"


def _seed_fuel_types(session) -> None:
    """Ensure the site's baseline fuel types exist (problemstatement.md #15:
    nozzles need a fuel type to dispense). Rates are left at 0.0 — the site
    must configure real prices, never guessed by the seed."""
    existing_names = {f.fuel_type for f in session.query(Fuel).all()}
    for fuel_type in DEFAULT_FUEL_TYPES:
        if fuel_type not in existing_names:
            session.add(Fuel(id=str(uuid.uuid4()), fuel_type=fuel_type, rate_per_liter=0.0))
    session.flush()


def _seed_tenders(session) -> dict:
    """Ensure the eight tenders docs/daily-report-spec.md's reference
    report shows exist (Tender, app/models/tender.py) - the same
    "seeded master data, not a hardcoded enum" pattern _seed_fuel_types
    already established for Fuel. Returns name -> Tender for
    _backfill_tender_ids to use without a second query.

    Also reconciles an existing tender's settlement_type against
    DEFAULT_TENDERS's current value, rather than only inserting once and
    leaving it be - the same "recompute rather than let it drift"
    discipline this project already applies to CreditAccount's
    outstanding balance and PurchaseOrder.status. This existed for a
    concrete reason, not hypothetically: "Other"'s settlement_type was
    wrong for one commit (IMMEDIATE_CASH, corrected to BANK_SETTLED -
    see DEFAULT_TENDERS's own comment), and without this reconciliation
    step, a database that had already run the old seed once would have
    stayed wrong forever even after the code was fixed.
    """
    existing = {t.name: t for t in session.query(Tender).all()}
    for name, settlement_type in DEFAULT_TENDERS:
        if name not in existing:
            tender = Tender(id=str(uuid.uuid4()), name=name, settlement_type=settlement_type.value)
            session.add(tender)
            existing[name] = tender
        elif existing[name].settlement_type != settlement_type.value:
            existing[name].settlement_type = settlement_type.value
    session.flush()
    return existing


def _backfill_tender_ids(session, tenders_by_name: dict) -> None:
    """One-time-per-row backfill for historical Sale/Payment/Expense rows
    recorded before Tender existed, plus a safety net for any row a
    future code path forgets to set tender_id on directly. Idempotent by
    construction (only ever touches rows where tender_id IS NULL), so
    running it on every startup is cheap once caught up.

    UPI rows map to "Other", not "PhonePe" or "Paytm" - PaymentMethod.UPI
    has never recorded which app was actually used, so this backfill
    cannot honestly claim either specific one. See
    PAYMENT_METHOD_TO_TENDER_NAME's own comment (app/core/constants.py)
    for the same reasoning applied going forward to new rows.
    """
    for model, method_column in ((Sale, "payment_method"), (Payment, "method"), (Expense, "payment_method")):
        rows = session.query(model).filter_by(tender_id=None).all()
        for row in rows:
            method_value = getattr(row, method_column)
            tender_name = PAYMENT_METHOD_TO_TENDER_NAME.get(method_value)
            if tender_name and tender_name in tenders_by_name:
                row.tender_id = tenders_by_name[tender_name].id
    session.flush()


def _seed_expense_categories(session) -> None:
    """Ensure the one ExpenseCategory this project seeds exists - "Cash
    Shortage", the category EmployeeShortageService.record_shortage
    books a reconciliation shortage's Expense side under (A2 in
    PROJECT_CONTEXT.md's working assumptions). Every other category
    remains entirely user-created via ExpenseService.create_category;
    this one exists only because the shortage feature must have
    somewhere reliable to book to without depending on every deployment
    having created an identically-named category by hand first."""
    existing = {c.name for c in session.query(ExpenseCategory).all()}
    if CASH_SHORTAGE_EXPENSE_CATEGORY_NAME not in existing:
        session.add(
            ExpenseCategory(
                id=str(uuid.uuid4()), name=CASH_SHORTAGE_EXPENSE_CATEGORY_NAME, status=StatusEnum.ACTIVE.value,
            )
        )
    session.flush()


def _seed_roles_and_permissions(session) -> dict:
    """Ensure every UserRole and Permission exists, and wire the RBAC matrix.

    Returns a dict of role name -> Role instance.
    """
    permissions_by_name = {p.name: p for p in session.query(Permission).all()}
    for perm in PermissionName:
        if perm.value not in permissions_by_name:
            permission = Permission(id=str(uuid.uuid4()), name=perm.value)
            session.add(permission)
            permissions_by_name[perm.value] = permission
    session.flush()

    roles_by_name = {r.name: r for r in session.query(Role).all()}
    for role in UserRole:
        if role.value not in roles_by_name:
            role_row = Role(
                id=str(uuid.uuid4()),
                name=role.value,
                description=f"{role.value.replace('_', ' ').title()} role",
            )
            session.add(role_row)
            roles_by_name[role.value] = role_row
    session.flush()

    for role, perms in ROLE_PERMISSIONS.items():
        role_row = roles_by_name[role.value]
        wanted = {permissions_by_name[p.value] for p in perms}
        current = set(role_row.permissions)
        for missing in wanted - current:
            role_row.permissions.append(missing)
    session.flush()

    return roles_by_name


def seed_initial_data() -> None:
    """Seed roles, permissions, and the initial admin user for the MVP run."""
    session = db_package.connection.SessionLocal()
    try:
        roles_by_name = _seed_roles_and_permissions(session)
        _seed_fuel_types(session)
        tenders_by_name = _seed_tenders(session)
        _backfill_tender_ids(session, tenders_by_name)
        _seed_expense_categories(session)

        existing_admin = session.query(User).filter_by(username="admin").first()
        if existing_admin:
            session.commit()
            return

        now = datetime.now(timezone.utc)
        admin_user = User(
            id=str(uuid.uuid4()),
            username="admin",
            email="admin@example.com",
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            first_name="Admin",
            last_name="User",
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            # DEFAULT_ADMIN_PASSWORD is a known, publicly-committed dev
            # credential - force it to be rotated on first real login
            # rather than trusting every deployment to remember to change it.
            must_change_password=True,
            role=roles_by_name[UserRole.ADMIN.value],
            created_at=now,
            updated_at=now,
        )
        session.add(admin_user)
        session.commit()
    finally:
        session.close()
