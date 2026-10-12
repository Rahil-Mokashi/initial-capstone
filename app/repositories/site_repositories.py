"""Repositories for the site-visit tables (lubricants, bowser, shift tender totals, internal fuel use).

Grouped in one module because each is small and they are only ever used together by the daily-report
services. Same conventions as the other repositories: insert/read, writes go through safe_commit.
"""

from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.bowser import BowserBill, BowserMeterReading, BowserOpening, BowserTransfer
from app.models.internal_fuel_use import InternalFuelUse
from app.models.lubricant import LubricantItem, LubricantMovement
from app.models.shift_tender_entry import ShiftTenderEntry
from app.repositories.base import safe_commit


class _Base:
    def __init__(self, session: Session):
        self._session = session

    def _add(self, row):
        self._session.add(row)
        safe_commit(self._session)
        self._session.refresh(row)
        return row

    def _save(self, row):
        safe_commit(self._session)
        self._session.refresh(row)
        return row


class LubricantItemRepository(_Base):
    def get_by_id(self, item_id: str) -> Optional[LubricantItem]:
        return self._session.query(LubricantItem).filter_by(id=item_id, is_deleted=False).first()

    def get_by_name(self, name: str) -> Optional[LubricantItem]:
        return self._session.query(LubricantItem).filter_by(name=name, is_deleted=False).first()

    def list_all(self) -> List[LubricantItem]:
        return self._session.query(LubricantItem).filter_by(is_deleted=False).order_by(LubricantItem.name).all()

    add = _Base._add
    update = _Base._save


class LubricantMovementRepository(_Base):
    def add(self, movement: LubricantMovement) -> LubricantMovement:
        return self._add(movement)

    def list_for_item(self, item_id: str) -> List[LubricantMovement]:
        return (
            self._session.query(LubricantMovement)
            .filter_by(item_id=item_id)
            .order_by(LubricantMovement.movement_date, LubricantMovement.created_at)
            .all()
        )

    def list_up_to(self, day: date) -> List[LubricantMovement]:
        """Everything on or before `day`, oldest first."""
        return (
            self._session.query(LubricantMovement)
            .filter(LubricantMovement.movement_date <= day)
            .order_by(LubricantMovement.movement_date, LubricantMovement.created_at)
            .all()
        )

    def list_for_day(self, day: date) -> List[LubricantMovement]:
        return (
            self._session.query(LubricantMovement)
            .filter_by(movement_date=day)
            .order_by(LubricantMovement.created_at)
            .all()
        )


class BowserRepository(_Base):
    # transfers
    def add_transfer(self, t: BowserTransfer) -> BowserTransfer:
        return self._add(t)

    def transfers_for_day(self, day: date) -> List[BowserTransfer]:
        return (
            self._session.query(BowserTransfer).filter_by(transfer_date=day).order_by(BowserTransfer.created_at).all()
        )

    def transfers_before(self, day: date) -> List[BowserTransfer]:
        return self._session.query(BowserTransfer).filter(BowserTransfer.transfer_date < day).all()

    # bills
    def add_bill(self, b: BowserBill) -> BowserBill:
        return self._add(b)

    def get_bill(self, bill_id: str) -> Optional[BowserBill]:
        return self._session.get(BowserBill, bill_id)

    def bills_for_day(self, day: date, include_void: bool = False) -> List[BowserBill]:
        q = self._session.query(BowserBill).filter_by(bill_date=day)
        if not include_void:
            q = q.filter_by(status="active")
        return q.order_by(BowserBill.created_at).all()

    def bills_for_customer(self, customer_id: str) -> List[BowserBill]:
        return (
            self._session.query(BowserBill)
            .filter_by(customer_id=customer_id, status="active")
            .order_by(BowserBill.bill_date, BowserBill.created_at)
            .all()
        )

    def bills_before(self, day: date) -> List[BowserBill]:
        return self._session.query(BowserBill).filter(BowserBill.bill_date < day, BowserBill.status == "active").all()

    def save_bill(self, b: BowserBill) -> BowserBill:
        return self._save(b)

    # meter
    def add_meter(self, m: BowserMeterReading) -> BowserMeterReading:
        return self._add(m)

    def meter_for_day(self, day: date) -> Optional[BowserMeterReading]:
        return (
            self._session.query(BowserMeterReading)
            .filter_by(reading_date=day, status="active")
            .order_by(BowserMeterReading.created_at.desc())
            .first()
        )

    def get_meter(self, meter_id: str) -> Optional[BowserMeterReading]:
        return self._session.get(BowserMeterReading, meter_id)

    def save_meter(self, m: BowserMeterReading) -> BowserMeterReading:
        return self._save(m)

    # opening
    def add_opening(self, o: BowserOpening) -> BowserOpening:
        return self._add(o)

    def opening_for_day(self, day: date) -> Optional[BowserOpening]:
        return (
            self._session.query(BowserOpening)
            .filter_by(opening_date=day, status="active")
            .order_by(BowserOpening.created_at.desc())
            .first()
        )

    def latest_opening_before_or_on(self, day: date) -> Optional[BowserOpening]:
        return (
            self._session.query(BowserOpening)
            .filter(BowserOpening.opening_date <= day, BowserOpening.status == "active")
            .order_by(BowserOpening.opening_date.desc(), BowserOpening.created_at.desc())
            .first()
        )


class ShiftTenderEntryRepository(_Base):
    def add(self, e: ShiftTenderEntry) -> ShiftTenderEntry:
        return self._add(e)

    def active_for_shift(self, shift_id: str) -> List[ShiftTenderEntry]:
        return (
            self._session.query(ShiftTenderEntry)
            .filter_by(shift_id=shift_id, voided_at=None)
            .order_by(ShiftTenderEntry.created_at)
            .all()
        )

    def active_for_shift_tender(self, shift_id: str, tender_id: str) -> Optional[ShiftTenderEntry]:
        return (
            self._session.query(ShiftTenderEntry)
            .filter_by(shift_id=shift_id, tender_id=tender_id, voided_at=None)
            .first()
        )

    def history_for_shift(self, shift_id: str) -> List[ShiftTenderEntry]:
        return (
            self._session.query(ShiftTenderEntry)
            .filter_by(shift_id=shift_id)
            .order_by(ShiftTenderEntry.created_at)
            .all()
        )

    def save(self, e: ShiftTenderEntry) -> ShiftTenderEntry:
        return self._save(e)


class InternalFuelUseRepository(_Base):
    def add(self, row: InternalFuelUse) -> InternalFuelUse:
        return self._add(row)

    def get_for_expense(self, expense_id: str) -> Optional[InternalFuelUse]:
        return self._session.query(InternalFuelUse).filter_by(expense_id=expense_id).first()


class ReportQueryRepository(_Base):
    """Read-only date-bounded queries the daily report needs that the older repositories do not offer."""

    def tank_transactions_since(self, tank_id: str, since_utc) -> list:
        from app.models.tank_transaction import TankTransaction

        return (
            self._session.query(TankTransaction)
            .filter(TankTransaction.tank_id == tank_id, TankTransaction.transaction_at >= since_utc)
            .order_by(TankTransaction.transaction_at)
            .all()
        )

    def tank_readings_between(self, tank_id: str, start_utc, end_utc) -> list:
        from app.models.tank_reading import TankReading

        return (
            self._session.query(TankReading)
            .filter(TankReading.tank_id == tank_id, TankReading.reading_at >= start_utc, TankReading.reading_at <= end_utc)
            .order_by(TankReading.reading_at)
            .all()
        )

    def fuel_reconciliation_for(self, tank_id: str, day: date):
        from app.models.fuel_reconciliation import FuelReconciliation

        return (
            self._session.query(FuelReconciliation)
            .filter_by(tank_id=tank_id, reconciliation_date=day)
            .order_by(FuelReconciliation.created_at.desc())
            .first()
        )

    def shifts_on(self, day: date) -> list:
        from app.models.shift import Shift

        return self._session.query(Shift).filter_by(shift_date=day).order_by(Shift.created_at).all()

    def recoveries_for_cash_book(self, cash_book_id: str) -> list:
        from app.models.employee_cash_shortage import EmployeeShortageRecovery

        return (
            self._session.query(EmployeeShortageRecovery)
            .filter_by(shift_cash_book_id=cash_book_id)
            .order_by(EmployeeShortageRecovery.recorded_at)
            .all()
        )
