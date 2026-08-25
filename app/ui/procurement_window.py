"""Procurement UI (Phase 10). Three tabs: Suppliers, Purchase Orders,
Invoices. The tanker-arrival-to-inventory-update delivery workflow lives
inside the purchase order detail dialog, since every delivery belongs to
one order. Pure presentation - validation and business rules live in
ProcurementService and its Pydantic schemas.
"""

from decimal import Decimal

from pydantic import ValidationError
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import FuelDeliveryStatus, Permission, PurchaseOrderStatus, SupplierInvoiceStatus
from app.core.exceptions import AppError
from app.database.base import StatusEnum
from app.schemas.fuel_delivery import FuelDeliveryArrive, FuelDeliveryDipReading
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderItemCreate
from app.schemas.supplier import SupplierCreate
from app.schemas.supplier_invoice import SupplierInvoiceCreate, SupplierPaymentCreate
from app.ui.qt_utils import apply_hard_shadow, chain_enter_to_next_field, describe_unexpected_error, qdate_to_date
from app.ui.widgets import GridBackgroundWidget

SUPPLIER_HEADERS = ["Name", "Contact", "Phone", "Status"]
PO_HEADERS = ["PO Number", "Supplier", "Order Date", "Status"]

# The same "still owed to us" statuses DashboardService's own pending-PO
# count uses - a PO this tab's card row should surface as a delivery
# still outstanding, not one already fully received or abandoned.
PENDING_DELIVERY_STATUSES = {
    PurchaseOrderStatus.DRAFT.value,
    PurchaseOrderStatus.PLACED.value,
    PurchaseOrderStatus.PARTIALLY_DELIVERED.value,
}
PENDING_DELIVERY_CARDS_SHOWN = 3
INVOICE_HEADERS = ["Invoice #", "Supplier", "Date", "Amount", "Status"]
ITEM_HEADERS = ["Fuel", "Quantity", "Rate/L"]
DELIVERY_HEADERS = ["Tanker", "Arrived", "Status", "Received"]
PAYMENT_HEADERS = ["Date", "Amount", "Method", "Reference"]


class ProcurementWindow(QWidget):
    def __init__(self, procurement_service, fuel_repo, tank_service, employee_service, auth_service, actor_user_id: str):
        super().__init__()
        self._procurement_service = procurement_service
        self._can_manage = auth_service.check_permission(actor_user_id, Permission.PROCUREMENT_MANAGE.value)

        self.setWindowTitle("Procurement")
        self.setMinimumSize(880, 600)

        title = QLabel("Procurement")
        title.setObjectName("title")

        self.supplier_tab = SupplierTab(procurement_service, actor_user_id, self._can_manage)
        self.po_tab = PurchaseOrderTab(
            procurement_service, fuel_repo, tank_service, employee_service, actor_user_id, self._can_manage
        )
        self.invoice_tab = InvoiceTab(procurement_service, actor_user_id, self._can_manage)

        tabs = QTabWidget()
        tabs.addTab(self.supplier_tab, "Suppliers")
        tabs.addTab(self.po_tab, "Purchase Orders")
        tabs.addTab(self.invoice_tab, "Invoices")
        tabs.currentChanged.connect(lambda _: (self.po_tab.refresh(), self.invoice_tab.refresh()))

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(tabs)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)


# ----------------------------------------------------------------------
# Suppliers
# ----------------------------------------------------------------------


class SupplierTab(QWidget):
    def __init__(self, procurement_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._procurement_service = procurement_service
        self._actor_user_id = actor_user_id
        self._can_manage = can_manage

        self.add_button = QPushButton("+ Add Supplier")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(SUPPLIER_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(SUPPLIER_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._toggle_selected_status)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        suppliers = self._procurement_service.list_suppliers(self._actor_user_id)
        self.table.setRowCount(len(suppliers))
        for row_index, supplier in enumerate(suppliers):
            self.table.setItem(row_index, 0, QTableWidgetItem(supplier.name))
            self.table.setItem(row_index, 1, QTableWidgetItem(supplier.contact_person or ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(supplier.phone or ""))
            self.table.setItem(row_index, 3, QTableWidgetItem(supplier.status.title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, supplier.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = SupplierFormDialog(self._procurement_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _toggle_selected_status(self) -> None:
        if not self._can_manage:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        supplier_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        current_status = self.table.item(rows[0].row(), 3).text().lower()
        new_status = StatusEnum.INACTIVE if current_status == "active" else StatusEnum.ACTIVE

        reason, ok = QInputDialog.getText(self, "Change status", f"Reason to mark {new_status.value}:")
        if not ok or not reason.strip():
            return
        try:
            self._procurement_service.set_supplier_status(self._actor_user_id, supplier_id, new_status, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not change status", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change status", describe_unexpected_error(exc))
        self.refresh()


class SupplierFormDialog(QDialog):
    def __init__(self, procurement_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._procurement_service = procurement_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Add Supplier")
        self.setMinimumWidth(380)

        self.name_input = QLineEdit()
        self.contact_person_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.address_input = QLineEdit()
        self.gst_input = QLineEdit()
        self.gst_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(
            self.name_input, self.contact_person_input, self.phone_input,
            self.email_input, self.address_input, self.gst_input,
        )

        form = QFormLayout()
        form.addRow("Name", self.name_input)
        form.addRow("Contact person", self.contact_person_input)
        form.addRow("Phone", self.phone_input)
        form.addRow("Email", self.email_input)
        form.addRow("Address", self.address_input)
        form.addRow("GST number", self.gst_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        try:
            data = SupplierCreate(
                name=self.name_input.text(),
                contact_person=self.contact_person_input.text().strip() or None,
                phone=self.phone_input.text().strip() or None,
                email=self.email_input.text().strip() or None,
                address=self.address_input.text().strip() or None,
                gst_number=self.gst_input.text().strip() or None,
            )
            self._procurement_service.create_supplier(self._actor_user_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


class PurchaseOrderDetailDialog(QDialog):
    def __init__(self, procurement_service, tank_service, employee_service, actor_user_id: str, po_id: str, can_manage: bool, parent=None):
        super().__init__(parent)
        self._procurement_service = procurement_service
        self._tank_service = tank_service
        self._employee_service = employee_service
        self._actor_user_id = actor_user_id
        self._po_id = po_id
        self._can_manage = can_manage
        self._po = procurement_service.get_purchase_order(actor_user_id, po_id)

        self.setWindowTitle(self._po.po_number)
        self.setMinimumSize(560, 520)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("sectionTitle")
        self.summary_label.setWordWrap(True)

        self.items_table = QTableWidget(0, len(ITEM_HEADERS))
        self.items_table.setAlternatingRowColors(True)
        self.items_table.setHorizontalHeaderLabels(ITEM_HEADERS)
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setMaximumHeight(120)

        self.arrival_button = QPushButton("Record Delivery Arrival")
        self.arrival_button.clicked.connect(self._record_arrival)
        self.cancel_order_button = QPushButton("Cancel Order")
        self.cancel_order_button.setObjectName("dangerButton")
        self.cancel_order_button.clicked.connect(self._cancel_order)

        action_row = QHBoxLayout()
        action_row.addWidget(self.arrival_button)
        action_row.addWidget(self.cancel_order_button)
        action_row.addStretch()

        self.deliveries_table = QTableWidget(0, len(DELIVERY_HEADERS))
        self.deliveries_table.setAlternatingRowColors(True)
        self.deliveries_table.setHorizontalHeaderLabels(DELIVERY_HEADERS)
        self.deliveries_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.deliveries_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.deliveries_table.verticalHeader().setVisible(False)
        self.deliveries_table.doubleClicked.connect(self._open_selected_delivery)

        close_button = QPushButton("Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.accept)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.addWidget(self.summary_label)
        layout.addWidget(QLabel("Items"))
        layout.addWidget(self.items_table)
        if can_manage:
            layout.addLayout(action_row)
        layout.addWidget(QLabel("Deliveries"))
        layout.addWidget(self.deliveries_table)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        self._po = self._procurement_service.get_purchase_order(self._actor_user_id, self._po_id)
        supplier_name = self._po.supplier.name if self._po.supplier else ""
        self.summary_label.setText(
            f"{self._po.po_number} — {supplier_name}\n"
            f"Status: {self._po.status.replace('_', ' ').title()}"
        )

        self.items_table.setRowCount(len(self._po.items))
        for row_index, item in enumerate(self._po.items):
            self.items_table.setItem(row_index, 0, QTableWidgetItem(item.fuel.fuel_type if item.fuel else ""))
            self.items_table.setItem(row_index, 1, QTableWidgetItem(f"{item.quantity_ordered:g}"))
            self.items_table.setItem(row_index, 2, QTableWidgetItem(f"{item.rate_per_liter:g}"))

        can_add_delivery = self._po.status in (
            PurchaseOrderStatus.PLACED.value, PurchaseOrderStatus.PARTIALLY_DELIVERED.value,
        )
        self.arrival_button.setEnabled(can_add_delivery)
        self.cancel_order_button.setEnabled(self._po.status == PurchaseOrderStatus.PLACED.value)

        deliveries = self._procurement_service.list_deliveries(self._actor_user_id, self._po_id)
        self.deliveries_table.setRowCount(len(deliveries))
        for row_index, delivery in enumerate(deliveries):
            self.deliveries_table.setItem(row_index, 0, QTableWidgetItem(delivery.tanker_number))
            self.deliveries_table.setItem(row_index, 1, QTableWidgetItem(delivery.arrived_at.strftime("%Y-%m-%d %H:%M")))
            self.deliveries_table.setItem(row_index, 2, QTableWidgetItem(delivery.status.replace("_", " ").title()))
            received = f"{delivery.quantity_received:g}" if delivery.quantity_received is not None else ""
            self.deliveries_table.setItem(row_index, 3, QTableWidgetItem(received))
            self.deliveries_table.item(row_index, 0).setData(Qt.UserRole, delivery.id)
        self.deliveries_table.resizeColumnsToContents()

    def _record_arrival(self) -> None:
        dialog = FuelDeliveryArrivalDialog(
            self._procurement_service, self._tank_service, self._employee_service,
            self._actor_user_id, self._po_id, self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _cancel_order(self) -> None:
        reason, ok = QInputDialog.getText(self, "Cancel purchase order", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._procurement_service.cancel_purchase_order(self._actor_user_id, self._po_id, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not cancel order", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not cancel order", describe_unexpected_error(exc))
        self.refresh()

    def _open_selected_delivery(self) -> None:
        rows = self.deliveries_table.selectionModel().selectedRows()
        if not rows:
            return
        delivery_id = self.deliveries_table.item(rows[0].row(), 0).data(Qt.UserRole)
        dialog = FuelDeliveryDetailDialog(self._procurement_service, self._actor_user_id, delivery_id, self._can_manage, self)
        dialog.exec()
        self.refresh()


class FuelDeliveryArrivalDialog(QDialog):
    def __init__(self, procurement_service, tank_service, employee_service, actor_user_id: str, po_id: str, parent=None):
        super().__init__(parent)
        self._procurement_service = procurement_service
        self._actor_user_id = actor_user_id
        self._po_id = po_id

        self.setWindowTitle("Record Delivery Arrival")
        self.setMinimumWidth(380)

        self.tank_combo = QComboBox()
        for tank in tank_service.list_tanks(actor_user_id):
            if tank.status == "active":
                self.tank_combo.addItem(f"{tank.code} ({tank.fuel.fuel_type if tank.fuel else ''})", tank.id)

        self.employee_combo = QComboBox()
        for employee in employee_service.list_employees(actor_user_id):
            self.employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

        self.tanker_number_input = QLineEdit()
        self.driver_name_input = QLineEdit()
        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(self.tanker_number_input, self.driver_name_input, self.remarks_input)

        form = QFormLayout()
        form.addRow("Tank", self.tank_combo)
        form.addRow("Received by", self.employee_combo)
        form.addRow("Tanker number", self.tanker_number_input)
        form.addRow("Driver name", self.driver_name_input)
        form.addRow("Remarks", self.remarks_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Record Arrival")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        if self.tank_combo.count() == 0:
            self._show_error("No active tanks available.")
            return
        if self.employee_combo.count() == 0:
            self._show_error("No employees available.")
            return
        try:
            data = FuelDeliveryArrive(
                purchase_order_id=self._po_id,
                tank_id=self.tank_combo.currentData(),
                received_by_employee_id=self.employee_combo.currentData(),
                tanker_number=self.tanker_number_input.text(),
                driver_name=self.driver_name_input.text().strip() or None,
                remarks=self.remarks_input.text().strip() or None,
            )
            self._procurement_service.record_delivery_arrival(self._actor_user_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


class FuelDeliveryDetailDialog(QDialog):
    """The Tanker Arrival -> ... -> Inventory Update workflow. Only the
    action valid for the delivery's current status is enabled at a
    time, so the workflow can't be skipped or run out of order from the
    UI (the service enforces this regardless - this just keeps the
    screen from offering a button that would fail)."""

    def __init__(self, procurement_service, actor_user_id: str, delivery_id: str, can_manage: bool, parent=None):
        super().__init__(parent)
        self._procurement_service = procurement_service
        self._actor_user_id = actor_user_id
        self._delivery_id = delivery_id
        self._can_manage = can_manage

        self.setWindowTitle("Delivery Detail")
        self.setMinimumWidth(420)

        self.status_label = QLabel()
        self.status_label.setObjectName("sectionTitle")
        self.status_label.setWordWrap(True)

        self.verify_documents_button = QPushButton("Verify Documents")
        self.verify_documents_button.clicked.connect(self._verify_documents)

        self.verify_quality_button = QPushButton("Verify Quality")
        self.verify_quality_button.clicked.connect(self._verify_quality)

        self.pre_dip_button = QPushButton("Record Pre-Dip Reading")
        self.pre_dip_button.clicked.connect(self._record_pre_dip)

        self.post_dip_button = QPushButton("Record Post-Dip & Unload")
        self.post_dip_button.clicked.connect(self._record_post_dip)

        self.reject_button = QPushButton("Reject Delivery")
        self.reject_button.setObjectName("dangerButton")
        self.reject_button.clicked.connect(self._reject)

        close_button = QPushButton("Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        if can_manage:
            layout.addWidget(self.verify_documents_button)
            layout.addWidget(self.verify_quality_button)
            layout.addWidget(self.pre_dip_button)
            layout.addWidget(self.post_dip_button)
            layout.addWidget(self.reject_button)
        layout.addWidget(close_button)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        delivery = self._procurement_service._get_delivery_or_raise(self._delivery_id)
        self._delivery = delivery
        lines = [f"Tanker {delivery.tanker_number} — {delivery.status.replace('_', ' ').title()}"]
        if delivery.pre_dip_value is not None:
            lines.append(f"Pre-dip: {delivery.pre_dip_value:g}")
        if delivery.post_dip_value is not None:
            lines.append(f"Post-dip: {delivery.post_dip_value:g}")
        if delivery.quantity_received is not None:
            lines.append(f"Received: {delivery.quantity_received:g} L")
        if delivery.rejection_reason:
            lines.append(f"Rejected: {delivery.rejection_reason}")
        self.status_label.setText("\n".join(lines))

        status = delivery.status
        self.verify_documents_button.setEnabled(status == FuelDeliveryStatus.ARRIVED.value)
        self.verify_quality_button.setEnabled(status == FuelDeliveryStatus.DOCUMENTS_VERIFIED.value)
        self.pre_dip_button.setEnabled(status == FuelDeliveryStatus.QUALITY_VERIFIED.value and delivery.pre_dip_value is None)
        self.post_dip_button.setEnabled(status == FuelDeliveryStatus.QUALITY_VERIFIED.value and delivery.pre_dip_value is not None)
        self.reject_button.setEnabled(
            status in (FuelDeliveryStatus.ARRIVED.value, FuelDeliveryStatus.DOCUMENTS_VERIFIED.value, FuelDeliveryStatus.QUALITY_VERIFIED.value)
        )

    def _verify_documents(self) -> None:
        self._run(lambda: self._procurement_service.verify_documents(self._actor_user_id, self._delivery_id))

    def _verify_quality(self) -> None:
        notes, ok = QInputDialog.getText(self, "Verify quality", "Notes (optional):")
        if not ok:
            return
        self._run(lambda: self._procurement_service.verify_quality(self._actor_user_id, self._delivery_id, notes.strip() or None))

    def _record_pre_dip(self) -> None:
        value, ok = QInputDialog.getDouble(self, "Pre-dip reading", "Dip value (L):", 0, 0, 10_000_000, 3)
        if not ok:
            return
        self._run(
            lambda: self._procurement_service.record_pre_dip(
                self._actor_user_id, self._delivery_id, FuelDeliveryDipReading(dip_value=Decimal(str(value)))
            )
        )

    def _record_post_dip(self) -> None:
        value, ok = QInputDialog.getDouble(self, "Post-dip reading", "Dip value (L):", 0, 0, 10_000_000, 3)
        if not ok:
            return
        self._run(
            lambda: self._procurement_service.record_post_dip_and_unload(
                self._actor_user_id, self._delivery_id, FuelDeliveryDipReading(dip_value=Decimal(str(value)))
            )
        )

    def _reject(self) -> None:
        reason, ok = QInputDialog.getText(self, "Reject delivery", "Reason:")
        if not ok or not reason.strip():
            return
        self._run(lambda: self._procurement_service.reject_delivery(self._actor_user_id, self._delivery_id, reason.strip()))

    def _run(self, action) -> None:
        try:
            action()
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not complete action", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not complete action", describe_unexpected_error(exc))
        self.refresh()


# ----------------------------------------------------------------------
# Purchase Orders
# ----------------------------------------------------------------------


class _PendingDeliveryCard(QWidget):
    """One outstanding purchase order, as a card - matching the reference
    design's "Pending Deliveries" row on the Deliveries screen. Takes the
    PurchaseOrder ORM object directly (read-only display, no business
    logic) rather than duplicating ProcurementService's own status
    classification here."""

    def __init__(self, po, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        status_label = QLabel(po.status.replace("_", " ").title())
        status_label.setObjectName("statusTagInactive")

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel(po.po_number))
        header_row.addStretch()
        header_row.addWidget(status_label)

        supplier_label = QLabel(po.supplier.name if po.supplier else "")
        supplier_label.setObjectName("dashCardTitle")

        fuel_types = ", ".join(sorted({item.fuel.fuel_type for item in po.items if item.fuel})) or "—"
        total_quantity = sum((item.quantity_ordered for item in po.items), Decimal("0"))
        detail_label = QLabel(f"{fuel_types}  •  {total_quantity:g} L")
        detail_label.setObjectName("subtitle")

        eta_text = po.expected_delivery_date.strftime("%d %b %Y") if po.expected_delivery_date else "No ETA set"
        eta_label = QLabel(eta_text)
        eta_label.setObjectName("subtitle")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        layout.addLayout(header_row)
        layout.addWidget(supplier_label)
        layout.addWidget(detail_label)
        layout.addWidget(eta_label)
        self.setLayout(layout)
        self.setMinimumWidth(220)

        apply_hard_shadow(self)


class PurchaseOrderTab(QWidget):
    def __init__(self, procurement_service, fuel_repo, tank_service, employee_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._procurement_service = procurement_service
        self._fuel_repo = fuel_repo
        self._tank_service = tank_service
        self._employee_service = employee_service
        self._actor_user_id = actor_user_id
        self._can_manage = can_manage

        self.add_button = QPushButton("+ Create Purchase Order")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        pending_label = QLabel("Pending Deliveries")
        pending_label.setObjectName("sectionTitle")
        self._pending_cards_layout = QHBoxLayout()
        self._pending_cards_layout.setSpacing(16)

        self.table = QTableWidget(0, len(PO_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(PO_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._open_selected)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(pending_label)
        layout.addLayout(self._pending_cards_layout)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.refresh()

    def _refresh_pending_cards(self, orders) -> None:
        while self._pending_cards_layout.count():
            item = self._pending_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        pending = [po for po in orders if po.status in PENDING_DELIVERY_STATUSES][:PENDING_DELIVERY_CARDS_SHOWN]
        if not pending:
            empty = QLabel("Nothing pending - every order is delivered or cleared.")
            empty.setObjectName("subtitle")
            self._pending_cards_layout.addWidget(empty)
            return

        for po in pending:
            self._pending_cards_layout.addWidget(_PendingDeliveryCard(po))
        self._pending_cards_layout.addStretch()

    def refresh(self) -> None:
        orders = self._procurement_service.list_purchase_orders(self._actor_user_id)
        self._refresh_pending_cards(orders)
        self.table.setRowCount(len(orders))
        for row_index, po in enumerate(orders):
            self.table.setItem(row_index, 0, QTableWidgetItem(po.po_number))
            self.table.setItem(row_index, 1, QTableWidgetItem(po.supplier.name if po.supplier else ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(po.order_date.strftime("%Y-%m-%d")))
            self.table.setItem(row_index, 3, QTableWidgetItem(po.status.replace("_", " ").title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, po.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = PurchaseOrderFormDialog(self._procurement_service, self._fuel_repo, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        po_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        dialog = PurchaseOrderDetailDialog(
            self._procurement_service, self._tank_service, self._employee_service,
            self._actor_user_id, po_id, self._can_manage, self,
        )
        dialog.exec()
        self.refresh()


class PurchaseOrderFormDialog(QDialog):
    def __init__(self, procurement_service, fuel_repo, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._procurement_service = procurement_service
        self._fuel_repo = fuel_repo
        self._actor_user_id = actor_user_id
        self._items: list[PurchaseOrderItemCreate] = []

        self.setWindowTitle("Create Purchase Order")
        self.setMinimumWidth(460)

        self.supplier_combo = QComboBox()
        for supplier in procurement_service.list_suppliers(actor_user_id):
            if supplier.status == StatusEnum.ACTIVE.value:
                self.supplier_combo.addItem(supplier.name, supplier.id)

        self.expected_delivery_input = QDateEdit(QDate.currentDate().addDays(3))
        self.expected_delivery_input.setCalendarPopup(True)

        self.remarks_input = QLineEdit()

        top_form = QFormLayout()
        top_form.addRow("Supplier", self.supplier_combo)
        top_form.addRow("Expected delivery", self.expected_delivery_input)
        top_form.addRow("Remarks", self.remarks_input)

        self.fuel_combo = QComboBox()
        for fuel in fuel_repo.list_active():
            self.fuel_combo.addItem(fuel.fuel_type, fuel.id)

        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setRange(0.01, 1_000_000)
        self.quantity_input.setDecimals(2)
        self.quantity_input.setValue(1000)

        self.rate_input = QDoubleSpinBox()
        self.rate_input.setRange(0.01, 100_000)
        self.rate_input.setDecimals(2)
        self.rate_input.setValue(95)

        self.add_item_button = QPushButton("+ Add Item")
        self.add_item_button.clicked.connect(self._add_item)

        item_row = QHBoxLayout()
        item_row.addWidget(self.fuel_combo, stretch=1)
        item_row.addWidget(self.quantity_input)
        item_row.addWidget(self.rate_input)
        item_row.addWidget(self.add_item_button)

        self.items_table = QTableWidget(0, len(ITEM_HEADERS))
        self.items_table.setAlternatingRowColors(True)
        self.items_table.setHorizontalHeaderLabels(ITEM_HEADERS)
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setMaximumHeight(140)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Create Order")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(top_form)
        layout.addWidget(QLabel("Order items"))
        layout.addLayout(item_row)
        layout.addWidget(self.items_table)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _add_item(self) -> None:
        if self.fuel_combo.count() == 0:
            self._show_error("No fuel types available.")
            return
        item = PurchaseOrderItemCreate(
            fuel_id=self.fuel_combo.currentData(),
            quantity_ordered=Decimal(str(self.quantity_input.value())),
            rate_per_liter=Decimal(str(self.rate_input.value())),
        )
        self._items.append(item)

        row_index = self.items_table.rowCount()
        self.items_table.insertRow(row_index)
        self.items_table.setItem(row_index, 0, QTableWidgetItem(self.fuel_combo.currentText()))
        self.items_table.setItem(row_index, 1, QTableWidgetItem(f"{item.quantity_ordered:g}"))
        self.items_table.setItem(row_index, 2, QTableWidgetItem(f"{item.rate_per_liter:g}"))
        self.error_label.hide()

    def _save(self) -> None:
        self.error_label.hide()
        if self.supplier_combo.count() == 0:
            self._show_error("No active suppliers available.")
            return
        if not self._items:
            self._show_error("Add at least one item to the order.")
            return
        try:
            data = PurchaseOrderCreate(
                supplier_id=self.supplier_combo.currentData(),
                expected_delivery_date=qdate_to_date(self.expected_delivery_input.date()),
                remarks=self.remarks_input.text().strip() or None,
                items=self._items,
            )
            self._procurement_service.create_purchase_order(self._actor_user_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


# ----------------------------------------------------------------------
# Invoices & Payments
# ----------------------------------------------------------------------


class InvoiceTab(QWidget):
    def __init__(self, procurement_service, actor_user_id: str, can_manage: bool):
        super().__init__()
        self._procurement_service = procurement_service
        self._actor_user_id = actor_user_id
        self._can_manage = can_manage

        self.add_button = QPushButton("+ Record Invoice")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)
        self.add_button.setVisible(can_manage)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(INVOICE_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(INVOICE_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._open_selected)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        invoices = self._procurement_service.list_invoices(self._actor_user_id)
        self.table.setRowCount(len(invoices))
        for row_index, invoice in enumerate(invoices):
            self.table.setItem(row_index, 0, QTableWidgetItem(invoice.invoice_number))
            self.table.setItem(row_index, 1, QTableWidgetItem(invoice.supplier.name if invoice.supplier else ""))
            self.table.setItem(row_index, 2, QTableWidgetItem(invoice.invoice_date.strftime("%Y-%m-%d")))
            self.table.setItem(row_index, 3, QTableWidgetItem(f"{invoice.amount:g}"))
            self.table.setItem(row_index, 4, QTableWidgetItem(invoice.status.replace("_", " ").title()))
            self.table.item(row_index, 0).setData(Qt.UserRole, invoice.id)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = SupplierInvoiceFormDialog(self._procurement_service, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        invoice_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        dialog = InvoiceDetailDialog(self._procurement_service, self._actor_user_id, invoice_id, self._can_manage, self)
        dialog.exec()
        self.refresh()


class SupplierInvoiceFormDialog(QDialog):
    def __init__(self, procurement_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._procurement_service = procurement_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Record Supplier Invoice")
        self.setMinimumWidth(400)

        self.invoice_number_input = QLineEdit()

        self.supplier_combo = QComboBox()
        for supplier in procurement_service.list_suppliers(actor_user_id):
            self.supplier_combo.addItem(supplier.name, supplier.id)

        self.po_combo = QComboBox()
        self.po_combo.addItem("(none)", None)
        for po in procurement_service.list_purchase_orders(actor_user_id):
            self.po_combo.addItem(po.po_number, po.id)

        self.invoice_date_input = QDateEdit(QDate.currentDate())
        self.invoice_date_input.setCalendarPopup(True)

        self.due_date_input = QDateEdit(QDate.currentDate().addDays(30))
        self.due_date_input.setCalendarPopup(True)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.01, 100_000_000)
        self.amount_input.setDecimals(2)

        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(self.invoice_number_input, self.remarks_input)

        form = QFormLayout()
        form.addRow("Invoice number", self.invoice_number_input)
        form.addRow("Supplier", self.supplier_combo)
        form.addRow("Purchase order", self.po_combo)
        form.addRow("Invoice date", self.invoice_date_input)
        form.addRow("Due date", self.due_date_input)
        form.addRow("Amount", self.amount_input)
        form.addRow("Remarks", self.remarks_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        if self.supplier_combo.count() == 0:
            self._show_error("No suppliers available.")
            return
        try:
            data = SupplierInvoiceCreate(
                invoice_number=self.invoice_number_input.text(),
                supplier_id=self.supplier_combo.currentData(),
                purchase_order_id=self.po_combo.currentData(),
                invoice_date=qdate_to_date(self.invoice_date_input.date()),
                due_date=qdate_to_date(self.due_date_input.date()),
                amount=Decimal(str(self.amount_input.value())),
                remarks=self.remarks_input.text().strip() or None,
            )
            self._procurement_service.create_invoice(self._actor_user_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


class InvoiceDetailDialog(QDialog):
    def __init__(self, procurement_service, actor_user_id: str, invoice_id: str, can_manage: bool, parent=None):
        super().__init__(parent)
        self._procurement_service = procurement_service
        self._actor_user_id = actor_user_id
        self._invoice_id = invoice_id
        self._can_manage = can_manage

        self.setWindowTitle("Invoice Detail")
        self.setMinimumSize(460, 420)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("sectionTitle")
        self.summary_label.setWordWrap(True)

        self.record_payment_button = QPushButton("Record Payment")
        self.record_payment_button.clicked.connect(self._record_payment)
        self.record_payment_button.setVisible(can_manage)

        self.payments_table = QTableWidget(0, len(PAYMENT_HEADERS))
        self.payments_table.setAlternatingRowColors(True)
        self.payments_table.setHorizontalHeaderLabels(PAYMENT_HEADERS)
        self.payments_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.payments_table.verticalHeader().setVisible(False)

        close_button = QPushButton("Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.accept)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.addWidget(self.summary_label)
        layout.addWidget(self.record_payment_button)
        layout.addWidget(QLabel("Payments"))
        layout.addWidget(self.payments_table)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        invoice = self._procurement_service._get_invoice_or_raise(self._invoice_id)
        supplier_name = invoice.supplier.name if invoice.supplier else ""
        self.summary_label.setText(
            f"{invoice.invoice_number} — {supplier_name}\n"
            f"Amount: {invoice.amount:g} — Status: {invoice.status.replace('_', ' ').title()}"
        )
        self.record_payment_button.setEnabled(invoice.status != SupplierInvoiceStatus.PAID.value)

        payments = self._procurement_service.list_payments(self._actor_user_id, self._invoice_id)
        self.payments_table.setRowCount(len(payments))
        for row_index, payment in enumerate(payments):
            self.payments_table.setItem(row_index, 0, QTableWidgetItem(payment.payment_date.strftime("%Y-%m-%d")))
            self.payments_table.setItem(row_index, 1, QTableWidgetItem(f"{payment.amount:g}"))
            self.payments_table.setItem(row_index, 2, QTableWidgetItem(payment.payment_method))
            self.payments_table.setItem(row_index, 3, QTableWidgetItem(payment.reference or ""))
        self.payments_table.resizeColumnsToContents()

    def _record_payment(self) -> None:
        dialog = SupplierPaymentFormDialog(self._procurement_service, self._actor_user_id, self._invoice_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()


class SupplierPaymentFormDialog(QDialog):
    def __init__(self, procurement_service, actor_user_id: str, invoice_id: str, parent=None):
        super().__init__(parent)
        self._procurement_service = procurement_service
        self._actor_user_id = actor_user_id
        self._invoice_id = invoice_id

        self.setWindowTitle("Record Payment")
        self.setMinimumWidth(360)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.01, 100_000_000)
        self.amount_input.setDecimals(2)

        self.payment_date_input = QDateEdit(QDate.currentDate())
        self.payment_date_input.setCalendarPopup(True)

        self.method_combo = QComboBox()
        self.method_combo.setEditable(True)
        self.method_combo.addItems(["Bank Transfer", "Cheque", "UPI", "Cash"])

        self.reference_input = QLineEdit()
        self.remarks_input = QLineEdit()
        self.remarks_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(self.reference_input, self.remarks_input)

        form = QFormLayout()
        form.addRow("Amount", self.amount_input)
        form.addRow("Payment date", self.payment_date_input)
        form.addRow("Method", self.method_combo)
        form.addRow("Reference", self.reference_input)
        form.addRow("Remarks", self.remarks_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        try:
            data = SupplierPaymentCreate(
                amount=Decimal(str(self.amount_input.value())),
                payment_date=qdate_to_date(self.payment_date_input.date()),
                payment_method=self.method_combo.currentText(),
                reference=self.reference_input.text().strip() or None,
                remarks=self.remarks_input.text().strip() or None,
            )
            self._procurement_service.record_payment(self._actor_user_id, self._invoice_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
