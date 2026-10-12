"""Lubricant items and their stock movements (the report's "Oil sale" table).

Stock is never stored: it is recomputed from the append-only movements, the same "recompute rather
than let it drift" rule used for credit balances and cash-in-hand. See app/models/lubricant.py.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import money, volume
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.models.lubricant import MOVEMENT_KINDS, LubricantItem, LubricantMovement
from app.repositories.base import session_for, unit_of_work


@dataclass
class LubricantStock:
    item: LubricantItem
    balance: Decimal


def signed_quantity(m: LubricantMovement) -> Decimal:
    """Effect of one movement on stock: a sale takes away, everything else adds (an adjustment is already signed)."""
    return -m.quantity if m.kind == "sale" else m.quantity


class LubricantService:
    def __init__(self, item_repo, movement_repo, shift_repo, audit_repo, auth_service):
        self._items = item_repo
        self._movements = movement_repo
        self._shift_repo = shift_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(item_repo)

    # -- items ------------------------------------------------------------------------------------------
    @require_permission(Permission.LUBRICANT_MANAGE.value)
    def create_item(self, actor_user_id: str, name: str, pack_size: Optional[str], default_rate: Decimal) -> LubricantItem:
        name = (name or "").strip()
        if not name:
            raise ValueError("Give the item a name")
        if default_rate < 0:
            raise ValueError("The rate cannot be negative")
        if self._items.get_by_name(name):
            raise ConflictError(f"An item named {name!r} already exists")
        with unit_of_work(self._session):
            item = self._items.add(LubricantItem(
                name=name, pack_size=(pack_size or "").strip() or None, default_rate=money(default_rate),
                status=StatusEnum.ACTIVE.value,
            ))
            self._audit_repo.record(
                event_type="lubricant_item_created", actor_id=actor_user_id, entity_type="LubricantItem",
                entity_id=item.id, description=f"Created lubricant item {name} at rate {item.default_rate}",
            )
            return item

    @require_permission(Permission.LUBRICANT_MANAGE.value)
    def set_default_rate(self, actor_user_id: str, item_id: str, new_rate: Decimal, reason: str) -> LubricantItem:
        if not (reason or "").strip():
            raise ValueError("A reason is required to change a rate")
        if new_rate < 0:
            raise ValueError("The rate cannot be negative")
        with unit_of_work(self._session):
            item = self._get_item(item_id)
            old = item.default_rate
            item.default_rate = money(new_rate)
            self._items.update(item)
            self._audit_repo.record(
                event_type="lubricant_rate_changed", actor_id=actor_user_id, entity_type="LubricantItem",
                entity_id=item.id, description=f"{item.name}: rate {old} -> {item.default_rate}. {reason.strip()}",
                old_value=str(old), new_value=str(item.default_rate),
            )
            return item

    @require_permission(Permission.LUBRICANT_VIEW.value)
    def list_items(self, actor_user_id: str, on: Optional[date] = None) -> List[LubricantStock]:
        on = on or date.today()
        balances = self._balances(on)
        return [LubricantStock(i, balances.get(i.id, Decimal("0"))) for i in self._items.list_all()]

    # -- movements --------------------------------------------------------------------------------------
    @require_permission(Permission.LUBRICANT_MANAGE.value)
    def record_movement(
        self, actor_user_id: str, item_id: str, kind: str, quantity: Decimal, movement_date: Optional[date] = None,
        unit_rate: Optional[Decimal] = None, shift_id: Optional[str] = None, customer_name: Optional[str] = None,
        remarks: Optional[str] = None,
    ) -> LubricantMovement:
        if kind not in MOVEMENT_KINDS:
            raise ValueError(f"Unknown movement kind: {kind}")
        quantity = volume(quantity)
        if quantity == 0:
            raise ValueError("The quantity cannot be zero")
        if kind != "adjustment" and quantity < 0:
            raise ValueError("The quantity must be more than zero")
        if kind == "adjustment" and not (remarks or "").strip():
            raise ValueError("A reason is required for a stock adjustment")
        with unit_of_work(self._session):
            item = self._get_item(item_id)
            amount = None
            if kind == "sale":
                if not shift_id:
                    raise ValueError("Pick the shift this sale belongs to")
                shift = self._shift_repo.get_by_id(shift_id)
                if shift is None:
                    raise NotFoundError(f"Shift not found: {shift_id}")
                movement_date = shift.shift_date  # the report groups sales by shift, so the shift decides the day
                unit_rate = money(unit_rate) if unit_rate is not None else item.default_rate
                amount = money(quantity * unit_rate)
            else:
                movement_date = movement_date or date.today()
                unit_rate = money(unit_rate) if unit_rate is not None else None
            row = self._movements.add(LubricantMovement(
                item_id=item.id, movement_date=movement_date, kind=kind, quantity=quantity, unit_rate=unit_rate,
                amount=amount, shift_id=shift_id if kind == "sale" else None,
                customer_name=(customer_name or "").strip() or None, remarks=(remarks or "").strip() or None,
                recorded_by_id=actor_user_id,
            ))
            self._audit_repo.record(
                event_type="lubricant_movement_recorded", actor_id=actor_user_id, entity_type="LubricantMovement",
                entity_id=row.id,
                description=f"{kind} {quantity} x {item.name}" + (f" at {unit_rate} = {amount}" if amount is not None else ""),
            )
            return row

    @require_permission(Permission.LUBRICANT_VIEW.value)
    def movements_for_item(self, actor_user_id: str, item_id: str) -> List[LubricantMovement]:
        self._get_item(item_id)
        return self._movements.list_for_item(item_id)

    # -- internal reads (the report builder and checks; no permission check on purpose) ------------------------
    def balance_before(self, item_id: str, day: date) -> Decimal:
        """Stock at the start of `day`."""
        return sum(
            (signed_quantity(m) for m in self._movements.list_for_item(item_id) if m.movement_date < day), Decimal("0")
        )

    def day_movements(self, day: date) -> List[LubricantMovement]:
        return self._movements.list_for_day(day)

    def _balances(self, on: date) -> dict:
        out: dict = {}
        for m in self._movements.list_up_to(on):
            out[m.item_id] = out.get(m.item_id, Decimal("0")) + signed_quantity(m)
        return out

    def _get_item(self, item_id: str) -> LubricantItem:
        item = self._items.get_by_id(item_id)
        if item is None:
            raise NotFoundError(f"Lubricant item not found: {item_id}")
        return item
