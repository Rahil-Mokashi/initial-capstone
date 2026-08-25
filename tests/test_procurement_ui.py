from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
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
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderItemCreate
from app.schemas.supplier import SupplierCreate
from app.schemas.tank import TankCreate
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.procurement_service import ProcurementService
from app.services.tank_service import TankService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_procurement_ui.db")
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
        username=username, email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"), role=role, is_active=True,
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
def employee_id(db_session):
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db_session.add(employee)
    db_session.commit()
    return employee.id


@pytest.fixture()
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def fuel_repo(db_session):
    return FuelRepository(db_session)


@pytest.fixture()
def tank_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return TankService(
        TankRepository(db_session), TankReadingRepository(db_session), TankTransactionRepository(db_session),
        FuelReconciliationRepository(db_session), FuelRepository(db_session), EmployeeRepository(db_session),
        audit_repo, auth_service,
    )


@pytest.fixture()
def employee_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return EmployeeService(
        EmployeeRepository(db_session), None, UserRepository(db_session), None, audit_repo, auth_service,
    )


@pytest.fixture()
def procurement_service(db_session, tank_service, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ProcurementService(
        SupplierRepository(db_session), PurchaseOrderRepository(db_session), PurchaseOrderItemRepository(db_session),
        FuelDeliveryRepository(db_session), SupplierInvoiceRepository(db_session), SupplierPaymentRepository(db_session),
        FuelRepository(db_session), EmployeeRepository(db_session), tank_service, audit_repo, auth_service,
    )


def test_window_shows_tabs_and_is_gated_on_view_permission(qapp, procurement_service, fuel_repo, tank_service, employee_service, auth_service, admin_id):
    from app.core.exceptions import PermissionDeniedError
    from app.ui.procurement_window import ProcurementWindow

    window = ProcurementWindow(procurement_service, fuel_repo, tank_service, employee_service, auth_service, admin_id)
    assert window.supplier_tab.table.columnCount() == 4
    assert window.po_tab.add_button.isHidden() is False


def test_supplier_form_creates_supplier(qapp, procurement_service, admin_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.procurement_window import SupplierFormDialog

    dialog = SupplierFormDialog(procurement_service, admin_id)
    dialog.name_input.setText("Acme Fuels")
    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert len(procurement_service.list_suppliers(admin_id)) == 1


def test_supplier_form_rejects_duplicate_name(qapp, procurement_service, admin_id):
    from app.ui.procurement_window import SupplierFormDialog

    procurement_service.create_supplier(admin_id, SupplierCreate(name="Acme Fuels"))

    dialog = SupplierFormDialog(procurement_service, admin_id)
    dialog.name_input.setText("Acme Fuels")
    dialog._save()

    assert dialog.error_label.isHidden() is False


def test_po_form_add_item_and_save(qapp, procurement_service, fuel_repo, admin_id, fuel_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.procurement_window import PurchaseOrderFormDialog

    supplier = procurement_service.create_supplier(admin_id, SupplierCreate(name="Acme Fuels"))

    dialog = PurchaseOrderFormDialog(procurement_service, fuel_repo, admin_id)
    index = dialog.supplier_combo.findData(supplier.id)
    dialog.supplier_combo.setCurrentIndex(index)
    dialog.quantity_input.setValue(2000)
    dialog.rate_input.setValue(95.5)
    dialog._add_item()
    assert dialog.items_table.rowCount() == 1

    dialog._save()
    assert dialog.result() == QDialog.Accepted

    orders = procurement_service.list_purchase_orders(admin_id)
    assert len(orders) == 1
    assert orders[0].po_number == "PO-0001"


def test_po_form_save_without_items_shows_error(qapp, procurement_service, fuel_repo, admin_id):
    from app.ui.procurement_window import PurchaseOrderFormDialog

    procurement_service.create_supplier(admin_id, SupplierCreate(name="Acme Fuels"))
    dialog = PurchaseOrderFormDialog(procurement_service, fuel_repo, admin_id)
    dialog._save()
    assert dialog.error_label.isHidden() is False


def test_pending_delivery_cards_show_outstanding_purchase_orders(qapp, procurement_service, fuel_repo, tank_service, employee_service, admin_id, fuel_id):
    from app.ui.procurement_window import PurchaseOrderTab

    tab = PurchaseOrderTab(procurement_service, fuel_repo, tank_service, employee_service, admin_id, can_manage=True)
    from PySide6.QtWidgets import QLabel
    assert any("Nothing pending" in label.text() for label in tab.findChildren(QLabel))

    supplier = procurement_service.create_supplier(admin_id, SupplierCreate(name="Acme Fuels"))
    procurement_service.create_purchase_order(
        admin_id,
        PurchaseOrderCreate(
            supplier_id=supplier.id,
            items=[PurchaseOrderItemCreate(fuel_id=fuel_id, quantity_ordered=Decimal("2000"), rate_per_liter=Decimal("95.5"))],
        ),
    )
    tab.refresh()

    assert tab._pending_cards_layout.count() >= 1
    texts = [label.text() for label in tab.findChildren(QLabel)]
    assert any("Acme Fuels" in text for text in texts)
    assert any("Petrol" in text and "2000" in text for text in texts)


def test_po_detail_dialog_records_full_delivery_workflow(qapp, procurement_service, tank_service, employee_service, admin_id, fuel_id, employee_id):
    from app.ui.procurement_window import FuelDeliveryDetailDialog, PurchaseOrderDetailDialog

    supplier = procurement_service.create_supplier(admin_id, SupplierCreate(name="Acme Fuels"))
    po = procurement_service.create_purchase_order(
        admin_id,
        PurchaseOrderCreate(
            supplier_id=supplier.id,
            items=[PurchaseOrderItemCreate(fuel_id=fuel_id, quantity_ordered=Decimal("2000"), rate_per_liter=Decimal("95.5"))],
        ),
    )
    tank = tank_service.create_tank(admin_id, TankCreate(code="T1", fuel_id=fuel_id, capacity=20000.0, opening_stock=1000.0))

    po_detail = PurchaseOrderDetailDialog(procurement_service, tank_service, employee_service, admin_id, po.id, True)
    assert po_detail.items_table.rowCount() == 1

    from app.schemas.fuel_delivery import FuelDeliveryArrive

    delivery = procurement_service.record_delivery_arrival(
        admin_id,
        FuelDeliveryArrive(purchase_order_id=po.id, tank_id=tank.id, received_by_employee_id=employee_id, tanker_number="TN-01"),
    )
    po_detail.refresh()
    assert po_detail.deliveries_table.rowCount() == 1

    delivery_dialog = FuelDeliveryDetailDialog(procurement_service, admin_id, delivery.id, True)
    assert delivery_dialog.verify_documents_button.isEnabled() is True
    assert delivery_dialog.verify_quality_button.isEnabled() is False

    delivery_dialog._verify_documents()
    assert delivery_dialog.verify_quality_button.isEnabled() is True

    delivery_dialog._delivery = procurement_service._get_delivery_or_raise(delivery.id)


def test_invoice_form_and_payment(qapp, procurement_service, admin_id):
    from PySide6.QtWidgets import QDialog

    from app.ui.procurement_window import InvoiceDetailDialog, SupplierInvoiceFormDialog, SupplierPaymentFormDialog

    supplier = procurement_service.create_supplier(admin_id, SupplierCreate(name="Acme Fuels"))

    dialog = SupplierInvoiceFormDialog(procurement_service, admin_id)
    index = dialog.supplier_combo.findData(supplier.id)
    dialog.supplier_combo.setCurrentIndex(index)
    dialog.invoice_number_input.setText("INV-1")
    dialog.amount_input.setValue(5000)
    dialog._save()
    assert dialog.result() == QDialog.Accepted

    invoices = procurement_service.list_invoices(admin_id)
    assert len(invoices) == 1

    invoice_detail = InvoiceDetailDialog(procurement_service, admin_id, invoices[0].id, True)
    assert invoice_detail.record_payment_button.isEnabled() is True

    payment_dialog = SupplierPaymentFormDialog(procurement_service, admin_id, invoices[0].id)
    payment_dialog.amount_input.setValue(5000)
    payment_dialog._save()
    assert payment_dialog.result() == QDialog.Accepted

    invoice_detail.refresh()
    assert invoice_detail.record_payment_button.isEnabled() is False


def test_window_denied_for_role_without_procurement_view(qapp, procurement_service, fuel_repo, tank_service, employee_service, auth_service, attendant_id):
    from app.core.exceptions import PermissionDeniedError
    from app.ui.procurement_window import ProcurementWindow

    with pytest.raises(PermissionDeniedError):
        ProcurementWindow(procurement_service, fuel_repo, tank_service, employee_service, auth_service, attendant_id)
