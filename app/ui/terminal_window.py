"""Terminal (2026-08-25, user-requested to match the "Quick Bill" screen of
a supplied reference design): a fast, big-tile sale-entry page, distinct
from the full Sales screen's list-and-dialog workflow.

Deliberately thin - it builds exactly the same SaleCreate SaleFormDialog
does (app/ui/sales_window.py) and calls the same SaleService.create_sale,
so a sale recorded here is identical in every respect (rate snapshotting,
tank issue, payment creation, credit-limit checks, audit logging) to one
recorded through the full Sales screen. This screen only changes how fast
an attendant can get there for the common case: their own current nozzle,
a round amount, a tap on a payment method.

Mirrors SaleFormDialog's existing branch: an attendant (no SHIFT_VIEW) gets
their current nozzle assignment auto-resolved via
ShiftService.get_my_active_assignment and shown as a read-only card: a
manager/supervisor (SHIFT_VIEW) gets full shift/employee pickers plus a
nozzle chip grid instead of a single auto-resolved nozzle.
"""

from decimal import Decimal, InvalidOperation

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import PaymentMethod, Permission
from app.core.exceptions import AppError
from app.database.base import StatusEnum
from app.schemas.sale import SaleCreate
from app.ui.qt_utils import apply_hard_shadow, describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget

# Common round rupee amounts a forecourt attendant is actually asked for -
# not an arbitrary progression, just what people hand over at the pump.
AMOUNT_PRESETS = (200, 500, 1000, 2000)

RECENT_SALES_LOOKBACK = 50   # how many of the newest sales to scan
RECENT_SALES_SHOWN = 5       # how many (already filtered to this nozzle) to display


class _Chip(QPushButton):
    """A checkable pill button used for the payment-method/mode/nozzle
    pickers - styled via QSS's native :checked pseudo-state (styles.py's
    QPushButton#chip), no manual property-polish dance needed."""

    def __init__(self, text: str, data=None, parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.data = data


class TerminalWindow(QWidget):
    def __init__(self, sale_service, shift_service, employee_service, auth_service, actor_user_id: str):
        super().__init__()
        self._sale_service = sale_service
        self._shift_service = shift_service
        self._employee_service = employee_service
        self._auth_service = auth_service
        self._actor_user_id = actor_user_id
        self._can_pick_freely = auth_service.check_permission(actor_user_id, Permission.SHIFT_VIEW.value)

        self._assignment = None          # self-service branch: resolved NozzleAssignment
        self._selected_nozzle = None     # free-pick branch: the chosen Nozzle
        self._nozzle_chips: list[_Chip] = []
        self._last_sale = None
        self._last_payment = None

        title = QLabel("Terminal")
        title.setObjectName("title")

        subtitle = QLabel("Fast fuel-sale entry - pick a nozzle, enter an amount, take payment.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        header = QVBoxLayout()
        header.setSpacing(4)
        header.addWidget(title)
        header.addWidget(subtitle)

        self._form_card = self._build_form_card()
        self._confirmation_card = self._build_confirmation_card()
        self._confirmation_card.setVisible(False)

        self._recent_title = QLabel("Recent sales on this nozzle")
        self._recent_title.setObjectName("sectionTitle")
        self._recent_layout = QVBoxLayout()
        self._recent_layout.setSpacing(8)
        recent_wrap = QVBoxLayout()
        recent_wrap.setSpacing(10)
        recent_wrap.addWidget(self._recent_title)
        recent_wrap.addLayout(self._recent_layout)
        self._recent_container = QWidget()
        self._recent_container.setLayout(recent_wrap)
        self._recent_container.setVisible(False)

        body = QVBoxLayout()
        body.setContentsMargins(24, 24, 24, 24)
        body.setSpacing(20)
        body.addLayout(header)
        body.addWidget(self._form_card)
        body.addWidget(self._confirmation_card)
        body.addWidget(self._recent_container)
        body.addStretch()

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(body)

        # A QScrollArea, not a bare widget - the free-pick branch (shift +
        # attendant pickers, a nozzle chip row, the amount/payment form,
        # and the recent-sales list) is taller than a typical window on a
        # short forecourt monitor. Without this, Qt has no choice but to
        # squeeze every row into whatever height it's given, which visibly
        # collapses and overlaps rows instead of scrolling - the same
        # reason SettingsWindow's form and the dashboard body scroll too.
        scroll = QScrollArea()
        scroll.setObjectName("background")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(container)

        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(scroll)

        self.refresh()

    # ------------------------------------------------------------------
    # Form construction
    # ------------------------------------------------------------------

    def _build_form_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        self._assignment_section = QVBoxLayout()
        self._assignment_section.setSpacing(10)
        layout.addLayout(self._assignment_section)

        # --- Amount / volume ------------------------------------------
        mode_label = QLabel("Amount")
        mode_label.setObjectName("sectionTitle")

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._rupee_chip = _Chip("₹ Amount")
        self._liters_chip = _Chip("Liters")
        self._rupee_chip.setChecked(True)
        for chip in (self._rupee_chip, self._liters_chip):
            self._mode_group.addButton(chip)
            chip.toggled.connect(self._on_mode_or_value_changed)

        mode_row = QHBoxLayout()
        mode_row.addWidget(mode_label)
        mode_row.addStretch()
        mode_row.addWidget(self._rupee_chip)
        mode_row.addWidget(self._liters_chip)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        self._preset_chips = []
        for amount in AMOUNT_PRESETS:
            chip = _Chip(f"₹{amount}", data=amount)
            chip.clicked.connect(lambda _checked=False, value=amount: self._apply_preset(value))
            preset_row.addWidget(chip)
            self._preset_chips.append(chip)
        preset_row.addStretch()

        self._amount_input = QDoubleSpinBox()
        self._amount_input.setRange(0.01, 500_000)
        self._amount_input.setDecimals(2)
        self._amount_input.setValue(500)
        self._amount_input.valueChanged.connect(self._on_mode_or_value_changed)

        self._preview_label = QLabel("")
        self._preview_label.setObjectName("statValue")

        layout.addLayout(mode_row)
        layout.addLayout(preset_row)
        layout.addWidget(self._amount_input)
        layout.addWidget(self._preview_label)

        # --- Payment method ---------------------------------------------
        payment_label = QLabel("Payment Method")
        payment_label.setObjectName("sectionTitle")

        # Built before the payment chips below, since checking the default
        # Cash chip fires _on_payment_method_changed synchronously (Qt
        # signals are not deferred to "after construction") and that
        # handler reads these widgets.
        self._customer_label = QLabel("Customer (required for credit)")
        self._customer_combo = QComboBox()

        self._reference_label = QLabel("UPI/Card reference")
        self._reference_input = QLineEdit()

        self._note_input = QLineEdit()
        self._note_input.setPlaceholderText("Optional - vehicle number, remark, etc.")

        self._payment_group = QButtonGroup(self)
        self._payment_group.setExclusive(True)
        payment_row = QHBoxLayout()
        payment_row.setSpacing(8)
        self._payment_chips: dict[PaymentMethod, _Chip] = {}
        for method in PaymentMethod:
            chip = _Chip(method.value.title(), data=method)
            chip.toggled.connect(self._on_payment_method_changed)
            self._payment_group.addButton(chip)
            payment_row.addWidget(chip)
            self._payment_chips[method] = chip
        self._payment_chips[PaymentMethod.CASH].setChecked(True)
        payment_row.addStretch()

        form = QFormLayout()
        form.addRow(self._customer_label, self._customer_combo)
        form.addRow(self._reference_label, self._reference_input)
        form.addRow("Note", self._note_input)

        layout.addWidget(payment_label)
        layout.addLayout(payment_row)
        layout.addLayout(form)

        self._error_label = QLabel("")
        self._error_label.setObjectName("errorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._submit_button = QPushButton("Complete Sale")
        self._submit_button.setCursor(Qt.PointingHandCursor)
        self._submit_button.clicked.connect(self._submit)
        layout.addWidget(self._submit_button)

        card.setLayout(layout)
        apply_hard_shadow(card)
        return card

    def _build_confirmation_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        heading = QLabel("Sale recorded")
        heading.setObjectName("title")

        self._receipt_summary = QLabel("")
        self._receipt_summary.setObjectName("subtitle")
        self._receipt_summary.setWordWrap(True)

        self._receipt_body = QLabel("")
        self._receipt_body.setObjectName("card")
        self._receipt_body.setAttribute(Qt.WA_StyledBackground, True)
        self._receipt_body.setWordWrap(True)
        self._receipt_body.setContentsMargins(16, 14, 16, 14)
        self._receipt_body.setStyleSheet("font-family: 'Consolas', monospace;")

        print_button = QPushButton("Print Receipt")
        print_button.setObjectName("secondaryButton")
        print_button.clicked.connect(self._print_receipt)

        export_button = QPushButton("Export PDF")
        export_button.setObjectName("secondaryButton")
        export_button.clicked.connect(self._export_receipt)

        new_sale_button = QPushButton("New Sale")
        new_sale_button.clicked.connect(self._start_new_sale)

        button_row = QHBoxLayout()
        button_row.addWidget(export_button)
        button_row.addWidget(print_button)
        button_row.addStretch()
        button_row.addWidget(new_sale_button)

        layout.addWidget(heading)
        layout.addWidget(self._receipt_summary)
        layout.addWidget(self._receipt_body)
        layout.addLayout(button_row)
        card.setLayout(layout)
        apply_hard_shadow(card)
        return card

    # ------------------------------------------------------------------
    # Assignment / nozzle resolution
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        self._clear_layout(self._assignment_section)
        self._nozzle_chips = []
        self._selected_nozzle = None
        self._assignment = None

        if self._can_pick_freely:
            self._build_free_pick_section()
        else:
            self._build_self_service_section()

        self._on_mode_or_value_changed()
        self._refresh_recent_sales()

    def _build_self_service_section(self) -> None:
        try:
            self._assignment = self._shift_service.get_my_active_assignment(self._actor_user_id)
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            self._assignment = None

        if self._assignment is None:
            info = QLabel("You have no active nozzle assignment - ask a supervisor to assign you one first.")
            info.setObjectName("subtitle")
            info.setWordWrap(True)
            self._assignment_section.addWidget(info)
            self._submit_button.setEnabled(False)
            return

        self._submit_button.setEnabled(True)
        nozzle = self._assignment.nozzle
        fuel_name = nozzle.fuel.fuel_type if nozzle and nozzle.fuel else ""
        card = QLabel(f"Selling from your current assignment: {nozzle.code if nozzle else ''}  —  {fuel_name}")
        card.setObjectName("statValue")
        card.setWordWrap(True)
        self._assignment_section.addWidget(card)

    def _build_free_pick_section(self) -> None:
        self._shift_combo = QComboBox()
        for shift in self._shift_service.list_shifts(self._actor_user_id):
            if shift.status == "open":
                self._shift_combo.addItem(f"{shift.shift_date} {shift.shift_label}", shift.id)

        self._employee_combo = QComboBox()
        for employee in self._employee_service.list_employees(self._actor_user_id):
            self._employee_combo.addItem(f"{employee.employee_code} - {employee.first_name} {employee.last_name}", employee.id)

        picker_form = QFormLayout()
        picker_form.addRow("Shift", self._shift_combo)
        picker_form.addRow("Attendant", self._employee_combo)
        self._assignment_section.addLayout(picker_form)

        nozzle_label = QLabel("Nozzle")
        nozzle_label.setObjectName("sectionTitle")
        self._assignment_section.addWidget(nozzle_label)

        nozzle_row = QHBoxLayout()
        nozzle_row.setSpacing(8)
        nozzle_group = QButtonGroup(self)
        nozzle_group.setExclusive(True)
        self._nozzle_group = nozzle_group
        nozzles = self._shift_service.list_active_nozzles(self._actor_user_id)
        for nozzle in nozzles:
            fuel_name = nozzle.fuel.fuel_type if nozzle.fuel else ""
            chip = _Chip(f"{nozzle.code}\n{fuel_name}", data=nozzle)
            chip.toggled.connect(self._on_nozzle_chip_toggled)
            nozzle_group.addButton(chip)
            nozzle_row.addWidget(chip)
            self._nozzle_chips.append(chip)
        nozzle_row.addStretch()
        self._assignment_section.addLayout(nozzle_row)

        if self._nozzle_chips:
            self._nozzle_chips[0].setChecked(True)
        self._submit_button.setEnabled(bool(self._nozzle_chips))
        if not self._nozzle_chips:
            empty = QLabel("No active nozzles available.")
            empty.setObjectName("subtitle")
            self._assignment_section.addWidget(empty)

    def _on_nozzle_chip_toggled(self) -> None:
        for chip in self._nozzle_chips:
            if chip.isChecked():
                self._selected_nozzle = chip.data
                break
        self._on_mode_or_value_changed()
        self._refresh_recent_sales()

    # ------------------------------------------------------------------
    # Live amount / volume preview
    # ------------------------------------------------------------------

    def _current_nozzle(self):
        if self._can_pick_freely:
            return self._selected_nozzle
        return self._assignment.nozzle if self._assignment else None

    def _current_rate(self) -> Decimal | None:
        nozzle = self._current_nozzle()
        if not nozzle or not nozzle.fuel or not nozzle.fuel.rate_per_liter:
            return None
        rate = Decimal(str(nozzle.fuel.rate_per_liter))
        return rate if rate > 0 else None

    def _apply_preset(self, amount: int) -> None:
        self._rupee_chip.setChecked(True)
        self._amount_input.setValue(float(amount))

    def _on_mode_or_value_changed(self, *_args) -> None:
        rate = self._current_rate()
        value = Decimal(str(self._amount_input.value()))

        if rate is None:
            nozzle = self._current_nozzle()
            if nozzle is not None:
                self._preview_label.setText("This fuel has no selling price set yet.")
            else:
                self._preview_label.setText("")
            return

        if self._rupee_chip.isChecked():
            amount = value
            quantity = (amount / rate).quantize(Decimal("0.01"))
        else:
            quantity = value
            amount = (quantity * rate).quantize(Decimal("0.01"))

        self._preview_label.setText(f"Volume: {quantity:g} L    Total: ₹{amount:,.2f}")

    def _on_payment_method_changed(self) -> None:
        method = self._selected_payment_method()
        is_credit = method == PaymentMethod.CREDIT
        needs_reference = method in (PaymentMethod.UPI, PaymentMethod.CARD)

        self._customer_label.setVisible(True)
        self._customer_combo.setVisible(True)
        self._reference_label.setVisible(needs_reference)
        self._reference_input.setVisible(needs_reference)
        self._customer_label.setText("Customer (required for credit)" if is_credit else "Customer")

        if self._customer_combo.count() == 0:
            self._customer_combo.addItem("(none)", None)
            for customer in self._sale_service.list_customers(self._actor_user_id):
                if customer.status == StatusEnum.ACTIVE.value:
                    self._customer_combo.addItem(customer.name, customer.id)

    def _selected_payment_method(self) -> PaymentMethod:
        for method, chip in self._payment_chips.items():
            if chip.isChecked():
                return method
        return PaymentMethod.CASH

    # ------------------------------------------------------------------
    # Recent sales on this nozzle
    # ------------------------------------------------------------------

    def _refresh_recent_sales(self) -> None:
        self._clear_layout(self._recent_layout)
        nozzle = self._current_nozzle()
        if nozzle is None:
            self._recent_container.setVisible(False)
            return

        try:
            recent = self._sale_service.list_sales(self._actor_user_id, limit=RECENT_SALES_LOOKBACK)
        except Exception:  # noqa: BLE001
            self._recent_container.setVisible(False)
            return

        matching = [sale for sale in recent if sale.nozzle_id == nozzle.id][:RECENT_SALES_SHOWN]
        if not matching:
            self._recent_container.setVisible(False)
            return

        self._recent_container.setVisible(True)
        for sale in matching:
            row = QLabel(
                f"{sale.sale_at.strftime('%H:%M')}   •   {sale.quantity:g} L   •   "
                f"₹{sale.amount:,.2f}   •   {sale.payment_method.title()}"
            )
            row.setObjectName("subtitle")
            self._recent_layout.addWidget(row)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        self._error_label.hide()

        if self._can_pick_freely:
            if self._shift_combo.count() == 0:
                self._show_error("No open shifts available.")
                return
            if self._employee_combo.count() == 0:
                self._show_error("No employees available.")
                return
            if self._selected_nozzle is None:
                self._show_error("Choose a nozzle first.")
                return
            shift_id = self._shift_combo.currentData()
            nozzle_id = self._selected_nozzle.id
            employee_id = self._employee_combo.currentData()
        elif self._assignment is not None:
            shift_id = self._assignment.shift_id
            nozzle_id = self._assignment.nozzle_id
            employee_id = self._assignment.employee_id
        else:
            self._show_error("You have no active nozzle assignment.")
            return

        rate = self._current_rate()
        if rate is None:
            self._show_error("This fuel has no selling price set - a manager must set it before this can be sold.")
            return

        value = Decimal(str(self._amount_input.value()))
        quantity = (value / rate) if self._rupee_chip.isChecked() else value

        method = self._selected_payment_method()
        try:
            data = SaleCreate(
                shift_id=shift_id,
                nozzle_id=nozzle_id,
                employee_id=employee_id,
                quantity=quantity,
                payment_method=method,
                customer_id=self._customer_combo.currentData(),
                reference_number=self._reference_input.text().strip() or None,
                remarks=self._note_input.text().strip() or None,
            )
            sale = self._sale_service.create_sale(self._actor_user_id, data)
        except (ValidationError, InvalidOperation) as exc:
            message = "; ".join(err["msg"] for err in exc.errors()) if isinstance(exc, ValidationError) else str(exc)
            self._show_error(message)
            return
        except AppError as exc:
            self._show_error(str(exc))
            return
        except ValueError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self._last_sale = sale
        try:
            self._last_payment = self._sale_service.get_payment_for_sale(self._actor_user_id, sale.id)
        except Exception:  # noqa: BLE001
            self._last_payment = None

        self._show_confirmation()

    def _show_confirmation(self) -> None:
        sale = self._last_sale
        self._receipt_summary.setText(f"Receipt {sale.receipt_number}  •  {sale.sale_at.strftime('%Y-%m-%d %H:%M')}")
        fuel_name = sale.fuel.fuel_type if sale.fuel else ""
        nozzle_code = sale.nozzle.code if sale.nozzle else ""
        lines = [
            f"Fuel: {fuel_name}",
            f"Nozzle: {nozzle_code}",
            f"Quantity: {sale.quantity:g} L",
            f"Rate/Litre: ₹{sale.rate_per_liter:.2f}",
            f"Amount: ₹{sale.amount:,.2f}",
            f"Payment: {sale.payment_method.title()}",
        ]
        if sale.customer:
            lines.append(f"Customer: {sale.customer.name}")
        self._receipt_body.setText("\n".join(lines))

        self._form_card.setVisible(False)
        self._confirmation_card.setVisible(True)
        self._refresh_recent_sales()

    def _start_new_sale(self) -> None:
        self._confirmation_card.setVisible(False)
        self._form_card.setVisible(True)
        self._last_sale = None
        self._last_payment = None
        self._amount_input.setValue(500)
        self._rupee_chip.setChecked(True)
        self._payment_chips[PaymentMethod.CASH].setChecked(True)
        self._reference_input.clear()
        self._note_input.clear()
        self.refresh()

    def _print_receipt(self) -> None:
        if self._last_sale is None:
            return
        from app.services.report_export import build_sale_receipt_html
        from app.ui.print_utils import show_print_preview

        show_print_preview(build_sale_receipt_html(self._last_sale, self._last_payment), self)

    def _export_receipt(self) -> None:
        if self._last_sale is None:
            return
        from app.core.paths import default_export_path
        from app.services.report_export import export_sale_receipt_pdf

        default_name = f"receipt_{self._last_sale.receipt_number}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export receipt", default_export_path(default_name), "PDF Files (*.pdf)"
        )
        if not file_path:
            return
        try:
            export_sale_receipt_pdf(self._last_sale, self._last_payment, file_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not export receipt", describe_unexpected_error(exc))
            return
        QMessageBox.information(self, "Export complete", f"Receipt saved to {file_path}")

    # ------------------------------------------------------------------

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
                continue
            child_layout = item.layout()
            if child_layout is not None:
                TerminalWindow._clear_layout(child_layout)
