from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import FuelDeliveryStatus, PurchaseOrderStatus, SupplierInvoiceStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base, StatusEnum
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_delivery_repository import FuelDeliveryRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.purchase_order_repository import PurchaseOrderItemRepository, PurchaseOrderRepository
from app.repositories.supplier_invoice_repository import SupplierInvoiceRepository, SupplierPaymentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.fuel_delivery import FuelDeliveryArrive, FuelDeliveryDipReading
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderItemCreate
from app.schemas.supplier import SupplierCreate
from app.schemas.supplier_invoice import SupplierInvoiceCreate, SupplierPaymentCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.procurement_service import ProcurementService
from app.services.tank_service import TankService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_procurement.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


def make_user(db_session, role_name: str, username: str) -> User:
    role = db_session.query(Role).filter_by(name=role_name).first()
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_id(db_session):
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


@pytest.fixture()
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def fuel_id(db_session):
    fuel = Fuel(fuel_type="Petrol", rate_per_liter=100.0)
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


@pytest.fixture()
def other_fuel_id(db_session):
    fuel = Fuel(fuel_type="Diesel", rate_per_liter=90.0)
    db_session.add(fuel)
    db_session.commit()
    return fuel.id


@pytest.fixture()
def employee_id(db_session):
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add(employee)
    db_session.commit()
    return employee.id


@pytest.fixture()
def tank_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return TankService(
        TankRepository(db_session),
        TankReadingRepository(db_session),
        TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session),
        FuelRepository(db_session),
        EmployeeRepository(db_session),
        audit_repo,
        auth_service,
    )


@pytest.fixture()
def procurement_service(db_session, tank_service):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return ProcurementService(
        SupplierRepository(db_session),
        PurchaseOrderRepository(db_session),
        PurchaseOrderItemRepository(db_session),
        FuelDeliveryRepository(db_session),
        SupplierInvoiceRepository(db_session),
        SupplierPaymentRepository(db_session),
        FuelRepository(db_session),
        EmployeeRepository(db_session),
        tank_service,
        audit_repo,
        auth_service,
    )


def make_supplier(procurement_service, admin_id, **overrides):
    defaults = dict(name="Acme Fuels")
    defaults.update(overrides)
    return procurement_service.create_supplier(admin_id, SupplierCreate(**defaults))


def make_tank(tank_service, admin_id, fuel_id, **overrides):
    defaults = dict(code="T1", fuel_id=fuel_id, capacity=10000.0, opening_stock=1000.0)
    defaults.update(overrides)
    return tank_service.create_tank(admin_id, TankCreate(**defaults))


def make_po(procurement_service, admin_id, supplier_id, fuel_id, **overrides):
    defaults = dict(
        supplier_id=supplier_id,
        items=[PurchaseOrderItemCreate(fuel_id=fuel_id, quantity_ordered=Decimal("5000"), rate_per_liter=Decimal("95.5"))],
    )
    defaults.update(overrides)
    return procurement_service.create_purchase_order(admin_id, PurchaseOrderCreate(**defaults))


# --------------------------------------------------------------------
# Suppliers
# --------------------------------------------------------------------

def test_create_supplier(procurement_service, admin_id):
    supplier = make_supplier(procurement_service, admin_id)
    assert supplier.name == "Acme Fuels"
    assert supplier.status == StatusEnum.ACTIVE.value


def test_duplicate_supplier_name_raises_conflict(procurement_service, admin_id):
    make_supplier(procurement_service, admin_id)
    with pytest.raises(ConflictError):
        make_supplier(procurement_service, admin_id)


def test_create_supplier_denied_without_permission(procurement_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        procurement_service.create_supplier(attendant_id, SupplierCreate(name="Acme Fuels"))


def test_set_supplier_status_requires_reason(procurement_service, admin_id):
    supplier = make_supplier(procurement_service, admin_id)
    with pytest.raises(ValueError):
        procurement_service.set_supplier_status(admin_id, supplier.id, StatusEnum.INACTIVE, "")


def test_set_supplier_status_records_audit_log(procurement_service, admin_id, db_session):
    supplier = make_supplier(procurement_service, admin_id)
    procurement_service.set_supplier_status(admin_id, supplier.id, StatusEnum.INACTIVE, "No longer supplying")
    events = {log.event_type for log in db_session.query(AuditLog).all()}
    assert "supplier_status_changed" in events


# --------------------------------------------------------------------
# Purchase Orders
# --------------------------------------------------------------------

def test_create_purchase_order(procurement_service, admin_id, fuel_id):
    supplier = make_supplier(procurement_service, admin_id)
    po = make_po(procurement_service, admin_id, supplier.id, fuel_id)
    assert po.po_number == "PO-0001"
    assert po.status == PurchaseOrderStatus.PLACED.value
    assert len(po.items) == 1


def test_purchase_order_numbers_are_sequential(procurement_service, admin_id, fuel_id):
    supplier = make_supplier(procurement_service, admin_id)
    first = make_po(procurement_service, admin_id, supplier.id, fuel_id)
    second = make_po(procurement_service, admin_id, supplier.id, fuel_id)
    assert first.po_number == "PO-0001"
    assert second.po_number == "PO-0002"


def test_purchase_order_rejects_unknown_fuel(procurement_service, admin_id):
    supplier = make_supplier(procurement_service, admin_id)
    with pytest.raises(NotFoundError):
        procurement_service.create_purchase_order(
            admin_id,
            PurchaseOrderCreate(
                supplier_id=supplier.id,
                items=[PurchaseOrderItemCreate(fuel_id="does-not-exist", quantity_ordered=Decimal("100"), rate_per_liter=Decimal("90"))],
            ),
        )


def test_purchase_order_rejects_inactive_supplier(procurement_service, admin_id, fuel_id):
    supplier = make_supplier(procurement_service, admin_id)
    procurement_service.set_supplier_status(admin_id, supplier.id, StatusEnum.INACTIVE, "Closed down")
    with pytest.raises(ConflictError):
        make_po(procurement_service, admin_id, supplier.id, fuel_id)


def test_purchase_order_schema_rejects_empty_items(fuel_id):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PurchaseOrderCreate(supplier_id="s1", items=[])


def test_cancel_purchase_order_requires_reason(procurement_service, admin_id, fuel_id):
    supplier = make_supplier(procurement_service, admin_id)
    po = make_po(procurement_service, admin_id, supplier.id, fuel_id)
    with pytest.raises(ValueError):
        procurement_service.cancel_purchase_order(admin_id, po.id, "")


def test_cancel_purchase_order(procurement_service, admin_id, fuel_id):
    supplier = make_supplier(procurement_service, admin_id)
    po = make_po(procurement_service, admin_id, supplier.id, fuel_id)
    cancelled = procurement_service.cancel_purchase_order(admin_id, po.id, "Supplier could not fulfil")
    assert cancelled.status == PurchaseOrderStatus.CANCELLED.value


def test_cannot_cancel_already_cancelled_order(procurement_service, admin_id, fuel_id):
    supplier = make_supplier(procurement_service, admin_id)
    po = make_po(procurement_service, admin_id, supplier.id, fuel_id)
    procurement_service.cancel_purchase_order(admin_id, po.id, "First cancel")
    with pytest.raises(ConflictError):
        procurement_service.cancel_purchase_order(admin_id, po.id, "Second cancel")


# --------------------------------------------------------------------
# Fuel Deliveries (the full workflow)
# --------------------------------------------------------------------

def _full_po_and_tank(procurement_service, tank_service, admin_id, fuel_id, quantity_ordered=Decimal("5000")):
    supplier = make_supplier(procurement_service, admin_id)
    po = make_po(
        procurement_service, admin_id, supplier.id, fuel_id,
        items=[PurchaseOrderItemCreate(fuel_id=fuel_id, quantity_ordered=quantity_ordered, rate_per_liter=Decimal("95.5"))],
    )
    tank = make_tank(tank_service, admin_id, fuel_id, capacity=20000.0, opening_stock=1000.0)
    return supplier, po, tank


def test_record_delivery_arrival(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    _, po, tank = _full_po_and_tank(procurement_service, tank_service, admin_id, fuel_id)
    delivery = procurement_service.record_delivery_arrival(
        admin_id,
        FuelDeliveryArrive(
            purchase_order_id=po.id, tank_id=tank.id, received_by_employee_id=employee_id, tanker_number="TN-01",
        ),
    )
    assert delivery.status == FuelDeliveryStatus.ARRIVED.value


def test_delivery_rejects_mismatched_fuel_type(procurement_service, tank_service, admin_id, fuel_id, other_fuel_id, employee_id):
    _, po, _ = _full_po_and_tank(procurement_service, tank_service, admin_id, fuel_id)
    diesel_tank = make_tank(tank_service, admin_id, other_fuel_id, code="T-diesel")
    with pytest.raises(ConflictError):
        procurement_service.record_delivery_arrival(
            admin_id,
            FuelDeliveryArrive(
                purchase_order_id=po.id, tank_id=diesel_tank.id, received_by_employee_id=employee_id, tanker_number="TN-01",
            ),
        )


def test_delivery_rejects_cancelled_purchase_order(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    _, po, tank = _full_po_and_tank(procurement_service, tank_service, admin_id, fuel_id)
    procurement_service.cancel_purchase_order(admin_id, po.id, "No longer needed")
    with pytest.raises(ConflictError):
        procurement_service.record_delivery_arrival(
            admin_id,
            FuelDeliveryArrive(
                purchase_order_id=po.id, tank_id=tank.id, received_by_employee_id=employee_id, tanker_number="TN-01",
            ),
        )


def _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id, quantity_ordered=Decimal("5000")):
    _, po, tank = _full_po_and_tank(procurement_service, tank_service, admin_id, fuel_id, quantity_ordered)
    delivery = procurement_service.record_delivery_arrival(
        admin_id,
        FuelDeliveryArrive(
            purchase_order_id=po.id, tank_id=tank.id, received_by_employee_id=employee_id, tanker_number="TN-01",
        ),
    )
    return po, tank, delivery


def test_full_delivery_workflow_updates_tank_stock(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    po, tank, delivery = _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id, Decimal("2000"))

    delivery = procurement_service.verify_documents(admin_id, delivery.id)
    assert delivery.status == FuelDeliveryStatus.DOCUMENTS_VERIFIED.value

    delivery = procurement_service.verify_quality(admin_id, delivery.id, notes="Sample clear")
    assert delivery.status == FuelDeliveryStatus.QUALITY_VERIFIED.value

    delivery = procurement_service.record_pre_dip(admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("1000")))
    assert delivery.pre_dip_value == Decimal("1000")

    delivery = procurement_service.record_post_dip_and_unload(
        admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("3000"))
    )
    assert delivery.status == FuelDeliveryStatus.UNLOADED.value
    assert delivery.quantity_received == Decimal("2000")
    assert delivery.tank_transaction_id is not None

    updated_tank = tank_service.get_tank(admin_id, tank.id)
    assert updated_tank.current_stock == Decimal("3000.000")

    updated_po = procurement_service.get_purchase_order(admin_id, po.id)
    assert updated_po.status == PurchaseOrderStatus.DELIVERED.value


def test_partial_delivery_leaves_po_partially_delivered(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    po, tank, delivery = _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id, Decimal("5000"))

    procurement_service.verify_documents(admin_id, delivery.id)
    procurement_service.verify_quality(admin_id, delivery.id)
    procurement_service.record_pre_dip(admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("1000")))
    procurement_service.record_post_dip_and_unload(admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("2000")))

    updated_po = procurement_service.get_purchase_order(admin_id, po.id)
    assert updated_po.status == PurchaseOrderStatus.PARTIALLY_DELIVERED.value


def test_post_dip_cannot_be_recorded_before_pre_dip(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    _, _, delivery = _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id)
    procurement_service.verify_documents(admin_id, delivery.id)
    procurement_service.verify_quality(admin_id, delivery.id)
    with pytest.raises(ConflictError):
        procurement_service.record_post_dip_and_unload(admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("2000")))


def test_post_dip_below_pre_dip_rejected(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    _, _, delivery = _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id)
    procurement_service.verify_documents(admin_id, delivery.id)
    procurement_service.verify_quality(admin_id, delivery.id)
    procurement_service.record_pre_dip(admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("1000")))
    with pytest.raises(ValueError):
        procurement_service.record_post_dip_and_unload(admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("500")))


def test_cannot_skip_document_verification(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    _, _, delivery = _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id)
    with pytest.raises(ConflictError):
        procurement_service.verify_quality(admin_id, delivery.id)


def test_reject_delivery_requires_reason(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    _, _, delivery = _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id)
    with pytest.raises(ValueError):
        procurement_service.reject_delivery(admin_id, delivery.id, "")


def test_reject_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    _, _, delivery = _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id)
    rejected = procurement_service.reject_delivery(admin_id, delivery.id, "Contaminated fuel sample")
    assert rejected.status == FuelDeliveryStatus.REJECTED.value
    assert rejected.rejection_reason == "Contaminated fuel sample"


def test_cannot_reject_an_unloaded_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id):
    _, _, delivery = _arrived_delivery(procurement_service, tank_service, admin_id, fuel_id, employee_id, Decimal("1000"))
    procurement_service.verify_documents(admin_id, delivery.id)
    procurement_service.verify_quality(admin_id, delivery.id)
    procurement_service.record_pre_dip(admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("1000")))
    procurement_service.record_post_dip_and_unload(admin_id, delivery.id, FuelDeliveryDipReading(dip_value=Decimal("2000")))
    with pytest.raises(ConflictError):
        procurement_service.reject_delivery(admin_id, delivery.id, "Too late")


# --------------------------------------------------------------------
# Supplier Invoices & Payments
# --------------------------------------------------------------------

def test_create_invoice(procurement_service, admin_id):
    supplier = make_supplier(procurement_service, admin_id)
    invoice = procurement_service.create_invoice(
        admin_id,
        SupplierInvoiceCreate(
            invoice_number="INV-100", supplier_id=supplier.id, invoice_date=date.today(), amount=Decimal("50000")
        ),
    )
    assert invoice.status == SupplierInvoiceStatus.UNPAID.value


def test_record_partial_payment(procurement_service, admin_id):
    supplier = make_supplier(procurement_service, admin_id)
    invoice = procurement_service.create_invoice(
        admin_id,
        SupplierInvoiceCreate(invoice_number="INV-100", supplier_id=supplier.id, invoice_date=date.today(), amount=Decimal("10000")),
    )
    procurement_service.record_payment(
        admin_id, invoice.id,
        SupplierPaymentCreate(amount=Decimal("4000"), payment_date=date.today(), payment_method="Bank Transfer"),
    )
    updated = procurement_service._get_invoice_or_raise(invoice.id)
    assert updated.status == SupplierInvoiceStatus.PARTIALLY_PAID.value


def test_record_payment_marks_invoice_paid_once_fully_covered(procurement_service, admin_id):
    supplier = make_supplier(procurement_service, admin_id)
    invoice = procurement_service.create_invoice(
        admin_id,
        SupplierInvoiceCreate(invoice_number="INV-100", supplier_id=supplier.id, invoice_date=date.today(), amount=Decimal("10000")),
    )
    procurement_service.record_payment(
        admin_id, invoice.id,
        SupplierPaymentCreate(amount=Decimal("10000"), payment_date=date.today(), payment_method="Bank Transfer"),
    )
    updated = procurement_service._get_invoice_or_raise(invoice.id)
    assert updated.status == SupplierInvoiceStatus.PAID.value


def test_payment_cannot_exceed_outstanding_balance(procurement_service, admin_id):
    supplier = make_supplier(procurement_service, admin_id)
    invoice = procurement_service.create_invoice(
        admin_id,
        SupplierInvoiceCreate(invoice_number="INV-100", supplier_id=supplier.id, invoice_date=date.today(), amount=Decimal("10000")),
    )
    with pytest.raises(ConflictError):
        procurement_service.record_payment(
            admin_id, invoice.id,
            SupplierPaymentCreate(amount=Decimal("10001"), payment_date=date.today(), payment_method="Bank Transfer"),
        )


def test_cannot_pay_an_already_fully_paid_invoice(procurement_service, admin_id):
    supplier = make_supplier(procurement_service, admin_id)
    invoice = procurement_service.create_invoice(
        admin_id,
        SupplierInvoiceCreate(invoice_number="INV-100", supplier_id=supplier.id, invoice_date=date.today(), amount=Decimal("10000")),
    )
    procurement_service.record_payment(
        admin_id, invoice.id,
        SupplierPaymentCreate(amount=Decimal("10000"), payment_date=date.today(), payment_method="Bank Transfer"),
    )
    with pytest.raises(ConflictError):
        procurement_service.record_payment(
            admin_id, invoice.id,
            SupplierPaymentCreate(amount=Decimal("1"), payment_date=date.today(), payment_method="Bank Transfer"),
        )


def test_accountant_can_view_but_not_manage_procurement(procurement_service, accountant_id, admin_id):
    make_supplier(procurement_service, admin_id)
    suppliers = procurement_service.list_suppliers(accountant_id)
    assert len(suppliers) == 1
    with pytest.raises(PermissionDeniedError):
        procurement_service.create_supplier(accountant_id, SupplierCreate(name="Another Supplier"))
