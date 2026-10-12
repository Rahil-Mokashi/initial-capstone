"""The bowser van: stock transfers in, delivery bills out, and its own meter.

A] internal stock = opening + each Stock Transfer (litres and rupees).
B] bills: Amount = Qty x rate (paise), Total = Amount + Transport.
C] meter: Net Sale = End - Start - Testing, which must equal the litres on the day's bills.
Closing Stock = A total litres - sum of bill litres.

A Stock Transfer is recorded as a CREDIT sale to an internal customer through SaleService, exactly as
the old report shows it ("Stock Transfer (Bouser)" among the credit sales), so the fuel leaves the tank,
counts in Total Sale, and the cash remainder at nozzle close shrinks by the same amount.

Nothing is edited or deleted: a wrong bill, meter reading or opening is voided with a reason.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from app.core.constants import PaymentMethod, Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import money, volume
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.models.bowser import BowserBill, BowserMeterReading, BowserOpening, BowserTransfer
from app.models.credit_account import CreditAccount
from app.models.customer import Customer
from app.repositories.base import session_for, unit_of_work
from app.schemas.sale import SaleCreate

BOWSER_CUSTOMER_NAME = "Stock Transfer (Bouser)"
# The internal customer is never chased for payment; this keeps the normal credit-limit check out of the way.
INTERNAL_CREDIT_LIMIT = Decimal("9999999999.99")
_Z = Decimal("0")


@dataclass
class StockLine:
    label: str
    litres: Decimal
    rupees: Decimal


@dataclass
class BowserDay:
    day: date
    stock_lines: List[StockLine] = field(default_factory=list)  # A: Opening Stock, then each Stock Transfer
    stock_litres: Decimal = _Z
    stock_rupees: Decimal = _Z
    bills: List[BowserBill] = field(default_factory=list)  # B
    bills_qty: Decimal = _Z
    bills_amount: Decimal = _Z
    bills_transport: Decimal = _Z
    bills_total: Decimal = _Z
    closing_litres: Decimal = _Z  # A total litres - bills qty
    closing_rupees: Decimal = _Z
    meter: Optional[BowserMeterReading] = None  # C
    meter_net: Optional[Decimal] = None


class BowserService:
    def __init__(self, bowser_repo, customer_repo, credit_account_repo, sale_service, shift_repo, audit_repo, auth_service):
        self._repo = bowser_repo
        self._customers = customer_repo
        self._accounts = credit_account_repo
        self._sales = sale_service
        self._shifts = shift_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(bowser_repo)

    # -- the internal customer --------------------------------------------------------------------------
    def internal_customer(self, actor_user_id: str) -> Customer:
        """The credit customer a Stock Transfer is billed to. Created on first use (an internal record, audited)."""
        customer = self._customers.get_by_name(BOWSER_CUSTOMER_NAME)
        if customer is None:
            customer = self._customers.add(Customer(name=BOWSER_CUSTOMER_NAME, status=StatusEnum.ACTIVE.value))
            self._audit_repo.record(
                event_type="bowser_customer_created", actor_id=actor_user_id, entity_type="Customer", entity_id=customer.id,
                description="Created the internal customer that Stock Transfers to the bowser are billed to",
            )
        if self._accounts.get_by_customer_id(customer.id) is None:
            self._accounts.add(CreditAccount(
                customer_id=customer.id, credit_limit=INTERNAL_CREDIT_LIMIT, payment_due_days=3650,
                created_by_id=actor_user_id,
            ))
        return customer

    # -- stock transfers ---------------------------------------------------------------------------------
    @require_permission(Permission.BOWSER_MANAGE.value)
    def record_transfer(self, actor_user_id: str, shift_id: str, nozzle_id: str, employee_id: str, litres: Decimal) -> BowserTransfer:
        litres = volume(litres)
        if litres <= 0:
            raise ValueError("The litres must be more than zero")
        with unit_of_work(self._session):
            shift = self._shifts.get_by_id(shift_id)
            if shift is None:
                raise NotFoundError(f"Shift not found: {shift_id}")
            customer = self.internal_customer(actor_user_id)
            sale = self._sales.create_sale(actor_user_id, SaleCreate(
                shift_id=shift_id, nozzle_id=nozzle_id, employee_id=employee_id, quantity=litres,
                payment_method=PaymentMethod.CREDIT, customer_id=customer.id,
                remarks="Stock Transfer to the bowser",
            ))
            row = self._repo.add_transfer(BowserTransfer(
                sale_id=sale.id, transfer_date=shift.shift_date, shift_id=shift_id, litres=sale.quantity,
                rate=sale.rate_per_liter, amount=sale.amount, recorded_by_id=actor_user_id,
            ))
            self._audit_repo.record(
                event_type="bowser_transfer_recorded", actor_id=actor_user_id, entity_type="BowserTransfer",
                entity_id=row.id, description=f"Stock Transfer {sale.quantity} L = {sale.amount} (sale {sale.receipt_number})",
            )
            return row

    # -- bills --------------------------------------------------------------------------------------------
    @require_permission(Permission.BOWSER_MANAGE.value)
    def record_bill(
        self, actor_user_id: str, bill_no: str, bill_date: date, customer_id: str, quantity: Decimal, rate: Decimal,
        transport: Decimal = _Z, vehicle_no: Optional[str] = None, slip_no: Optional[str] = None,
        shift_id: Optional[str] = None,
    ) -> BowserBill:
        bill_no = (bill_no or "").strip()
        if not bill_no:
            raise ValueError("Write the bill number")
        quantity, rate, transport = volume(quantity), money(rate), money(transport)
        if quantity <= 0:
            raise ValueError("The quantity must be more than zero")
        if rate < 0 or transport < 0:
            raise ValueError("The rate and transport cannot be negative")
        with unit_of_work(self._session):
            customer = self._customers.get_by_id(customer_id)
            if customer is None:
                raise NotFoundError(f"Customer not found: {customer_id}")
            if customer.name == BOWSER_CUSTOMER_NAME:
                raise ValueError("Pick the client the diesel was delivered to, not the Stock Transfer account")
            if any(b.bill_no == bill_no for b in self._repo.bills_for_day(bill_date)):
                raise ConflictError(f"Bill {bill_no} is already recorded for {bill_date}")
            amount = money(quantity * rate)
            row = self._repo.add_bill(BowserBill(
                bill_no=bill_no, bill_date=bill_date, customer_id=customer_id, quantity=quantity, rate=rate,
                amount=amount, transport=transport, total=amount + transport,
                vehicle_no=(vehicle_no or "").strip() or None, slip_no=(slip_no or "").strip() or None,
                shift_id=shift_id, status="active", recorded_by_id=actor_user_id,
            ))
            self._audit_repo.record(
                event_type="bowser_bill_recorded", actor_id=actor_user_id, entity_type="BowserBill", entity_id=row.id,
                description=f"Bowser bill {bill_no} to {customer.name}: {quantity} L x {rate} = {amount} + transport {transport} = {row.total}",
            )
            return row

    @require_permission(Permission.BOWSER_MANAGE.value)
    def void_bill(self, actor_user_id: str, bill_id: str, reason: str) -> BowserBill:
        if not (reason or "").strip():
            raise ValueError("A reason is required to void a bill")
        with unit_of_work(self._session):
            bill = self._repo.get_bill(bill_id)
            if bill is None:
                raise NotFoundError(f"Bowser bill not found: {bill_id}")
            if bill.status == "void":
                raise ConflictError("This bill is already void")
            bill.status, bill.void_reason, bill.voided_at = "void", reason.strip(), datetime.now(timezone.utc)
            self._repo.save_bill(bill)
            self._audit_repo.record(
                event_type="bowser_bill_voided", actor_id=actor_user_id, entity_type="BowserBill", entity_id=bill.id,
                description=f"Voided bowser bill {bill.bill_no} ({bill.total}): {reason.strip()}",
            )
            return bill

    # -- meter and opening ----------------------------------------------------------------------------------
    @require_permission(Permission.BOWSER_MANAGE.value)
    def record_meter(self, actor_user_id: str, day: date, start: Decimal, testing: Decimal, end: Decimal) -> BowserMeterReading:
        start, testing, end = volume(start), volume(testing), volume(end)
        if end < start:
            raise ValueError("The end reading cannot be below the start reading")
        if testing < 0:
            raise ValueError("Testing cannot be negative")
        with unit_of_work(self._session):
            old = self._repo.meter_for_day(day)
            if old is not None:
                old.status, old.void_reason, old.voided_at = "void", "Replaced by a new reading", datetime.now(timezone.utc)
                self._repo.save_meter(old)
            row = self._repo.add_meter(BowserMeterReading(
                reading_date=day, start_reading=start, testing=testing, end_reading=end, status="active",
                recorded_by_id=actor_user_id,
            ))
            self._audit_repo.record(
                event_type="bowser_meter_recorded", actor_id=actor_user_id, entity_type="BowserMeterReading", entity_id=row.id,
                description=f"{day}: start {start}, testing {testing}, end {end}, net {end - start - testing}"
                + (f" (replaces {old.start_reading}/{old.end_reading})" if old is not None else ""),
            )
            return row

    @require_permission(Permission.BOWSER_MANAGE.value)
    def set_opening(self, actor_user_id: str, day: date, litres: Decimal, rupees: Decimal, reason: str) -> BowserOpening:
        if not (reason or "").strip():
            raise ValueError("A reason is required to set the bowser's opening stock by hand")
        litres, rupees = volume(litres), money(rupees)
        if litres < 0 or rupees < 0:
            raise ValueError("Opening stock cannot be negative")
        with unit_of_work(self._session):
            old = self._repo.opening_for_day(day)
            if old is not None:
                old.status, old.voided_at = "void", datetime.now(timezone.utc)
                self._session.flush()
            row = self._repo.add_opening(BowserOpening(
                opening_date=day, litres=litres, rupees=rupees, reason=reason.strip(), status="active",
                recorded_by_id=actor_user_id,
            ))
            self._audit_repo.record(
                event_type="bowser_opening_set", actor_id=actor_user_id, entity_type="BowserOpening", entity_id=row.id,
                description=f"{day}: opening stock {litres} L / {rupees}. {reason.strip()}",
            )
            return row

    # -- the day, as the report needs it ------------------------------------------------------------------------
    @require_permission(Permission.BOWSER_VIEW.value)
    def day(self, actor_user_id: str, day: date) -> BowserDay:
        return self.build_day(day)

    def build_day(self, day: date) -> BowserDay:
        """Internal (no permission check): the report builder and the checks use this."""
        open_l, open_rs = self._position_before(day)
        out = BowserDay(day=day)
        out.stock_lines.append(StockLine("Opening Stock", open_l, open_rs))
        for t in self._repo.transfers_for_day(day):
            out.stock_lines.append(StockLine("Stock Transfer", t.litres, t.amount))
        out.stock_litres = sum((s.litres for s in out.stock_lines), _Z)
        out.stock_rupees = sum((s.rupees for s in out.stock_lines), _Z)
        out.bills = self._repo.bills_for_day(day)
        out.bills_qty = sum((b.quantity for b in out.bills), _Z)
        out.bills_amount = sum((b.amount for b in out.bills), _Z)
        out.bills_transport = sum((b.transport for b in out.bills), _Z)
        out.bills_total = sum((b.total for b in out.bills), _Z)
        out.closing_litres = out.stock_litres - out.bills_qty
        avg = (out.stock_rupees / out.stock_litres) if out.stock_litres else _Z
        out.closing_rupees = money(out.stock_rupees - out.bills_qty * avg)
        out.meter = self._repo.meter_for_day(day)
        if out.meter is not None:
            out.meter_net = out.meter.end_reading - out.meter.start_reading - out.meter.testing
        return out

    def _position_before(self, day: date):
        """(litres, rupees) the bowser holds at the start of `day`, valued at weighted-average cost.

        Starts from the latest manual opening on or before `day` (if any), then applies every transfer and
        bill of the days in between, in date order. Rupees follow the litres: a bill takes stock out at the
        running average cost. (T-13: how the owner values the opening stock is open; this is the default.)
        """
        manual = self._repo.latest_opening_before_or_on(day)
        litres, rupees = _Z, _Z
        start: Optional[date] = None
        if manual is not None:
            start = manual.opening_date
            litres, rupees = manual.litres, manual.rupees
        events = []
        for t in self._repo.transfers_before(day):
            if start is None or t.transfer_date >= start:
                events.append((t.transfer_date, 0, t.litres, t.amount))
        for b in self._repo.bills_before(day):
            if start is None or b.bill_date >= start:
                events.append((b.bill_date, 1, b.quantity, _Z))
        if manual is not None and manual.opening_date == day:
            return litres, rupees
        for _, kind, qty, rs in sorted(events, key=lambda e: (e[0], e[1])):
            if kind == 0:
                litres, rupees = litres + qty, rupees + rs
            else:
                avg = (rupees / litres) if litres else _Z
                litres, rupees = litres - qty, rupees - qty * avg
        return litres, money(rupees)
