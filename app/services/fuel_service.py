"""Fuel master data and selling prices.

This closes what was the single largest functional gap in the
application. seed.py creates Petrol, Diesel and Power with
rate_per_liter = 0.00, and until now *nothing in the app could change
that*: the only write to Fuel.rate_per_liter anywhere in the codebase
was that one seed line, and every other reference read it. There was no
fuel master-data screen and no service owning it.

So on a fresh install every sale computed quantity x 0.00 = 0.00, and
sales, payments, credit balances, reconciliation, the dashboard KPIs and
the whole Business Insights module all reported zero. The demo seeder
hid it by writing prices directly into the table.

Two decisions worth stating, because they are not obvious:

1. Changing a price requires FUEL_PRICE_MANAGE, a stricter permission
   than INVENTORY_MANAGE. Repricing silently changes the revenue of
   every future sale, which is a materially more consequential act than
   recording a stock movement - the same reasoning that gave
   shift.reopen and expense.approve their own separate grants.

2. Every change appends a FuelPriceHistory row as well as updating the
   cell. The cell answers "what is the price now", which is all a new
   sale needs; the history answers "what was it on the 14th, and who
   changed it", which is what an audit needs. Both, in one transaction.
"""

from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import money
from app.core.permissions import require_permission
from app.models.fuel import Fuel
from app.models.fuel_price_history import FuelPriceHistory
from app.repositories.base import session_for, unit_of_work
from app.schemas.fuel import FuelCreate, FuelRateChange


class FuelService:
    def __init__(self, fuel_repo, price_history_repo, audit_repo, auth_service):
        self._fuel_repo = fuel_repo
        self._price_history_repo = price_history_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(fuel_repo)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @require_permission(Permission.FUEL_PRICE_VIEW.value)
    def list_fuels(self, actor_user_id: str) -> List[Fuel]:
        return self._fuel_repo.list_active()

    @require_permission(Permission.FUEL_PRICE_VIEW.value)
    def get_fuel(self, actor_user_id: str, fuel_id: str) -> Fuel:
        return self._get_fuel_or_raise(fuel_id)

    @require_permission(Permission.FUEL_PRICE_VIEW.value)
    def get_price_history(self, actor_user_id: str, fuel_id: str) -> List[FuelPriceHistory]:
        self._get_fuel_or_raise(fuel_id)
        return self._price_history_repo.list_for_fuel(fuel_id)

    @require_permission(Permission.FUEL_PRICE_VIEW.value)
    def list_unpriced_fuels(self, actor_user_id: str) -> List[Fuel]:
        """Fuels that still carry the seeded 0.00 placeholder.

        Surfaced so the dashboard can warn about it rather than letting
        an operator discover it by selling a tank of petrol for nothing.
        """
        return [f for f in self._fuel_repo.list_active() if not self._is_priced(f)]

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    @require_permission(Permission.FUEL_PRICE_MANAGE.value)
    def set_rate(self, actor_user_id: str, fuel_id: str, data: FuelRateChange) -> Fuel:
        """Change a fuel's selling price, recording who and why.

        The cell update and the history row are one transaction: a price
        that changed with no record of the change is exactly the silent
        rewrite of financial data CLAUDE.md forbids.
        """
        with unit_of_work(self._session):
            fuel = self._get_fuel_or_raise(fuel_id)

            new_rate = money(data.new_rate_per_liter)
            old_rate = Decimal(str(fuel.rate_per_liter)) if fuel.rate_per_liter is not None else None

            if old_rate is not None and money(old_rate) == new_rate:
                raise ConflictError(
                    f"{fuel.fuel_type} is already priced at {new_rate}; no change to record"
                )

            self._price_history_repo.add(
                FuelPriceHistory(
                    fuel_id=fuel.id,
                    # The seeded 0.00 is a placeholder, not a price anyone
                    # set, so the first real price has no predecessor.
                    old_rate_per_liter=old_rate if (old_rate and old_rate > 0) else None,
                    new_rate_per_liter=new_rate,
                    reason=data.reason,
                    changed_by_id=actor_user_id,
                )
            )

            fuel.rate_per_liter = new_rate
            fuel = self._fuel_repo.update(fuel)

            self._audit_repo.record(
                event_type="fuel_price_changed",
                actor_id=actor_user_id,
                entity_type="Fuel",
                entity_id=fuel.id,
                description=(
                    f"{fuel.fuel_type} price {old_rate if old_rate else 'unset'} -> {new_rate}: {data.reason}"
                ),
            )
            return fuel

    @require_permission(Permission.FUEL_PRICE_MANAGE.value)
    def create_fuel(self, actor_user_id: str, data: FuelCreate) -> Fuel:
        existing = [f for f in self._fuel_repo.list_active() if f.fuel_type.lower() == data.fuel_type.lower()]
        if existing:
            raise ConflictError(f"A fuel type named {data.fuel_type} already exists")

        with unit_of_work(self._session):
            fuel = self._fuel_repo.add(
                Fuel(fuel_type=data.fuel_type, rate_per_liter=money(data.rate_per_liter), is_active=True)
            )
            if fuel.rate_per_liter and Decimal(str(fuel.rate_per_liter)) > 0:
                self._price_history_repo.add(
                    FuelPriceHistory(
                        fuel_id=fuel.id,
                        old_rate_per_liter=None,
                        new_rate_per_liter=money(data.rate_per_liter),
                        reason="Initial price set when the fuel type was created",
                        changed_by_id=actor_user_id,
                    )
                )
            self._audit_repo.record(
                event_type="fuel_created",
                actor_id=actor_user_id,
                entity_type="Fuel",
                entity_id=fuel.id,
                description=f"Created fuel type {fuel.fuel_type} at {fuel.rate_per_liter}",
            )
            return fuel

    # ------------------------------------------------------------------
    # Shared guard, used by SaleService
    # ------------------------------------------------------------------

    @staticmethod
    def _is_priced(fuel: Fuel) -> bool:
        return fuel.rate_per_liter is not None and Decimal(str(fuel.rate_per_liter)) > 0

    @staticmethod
    def ensure_fuel_is_priced(fuel: Fuel) -> None:
        """Reject a sale of a fuel that has never been priced.

        Deliberately a plain static helper with no @require_permission:
        it is called by SaleService as part of recording a sale, an
        action the attendant is already authorized for under
        SALE_MANAGE. Re-checking a *different* permission here would
        reproduce exactly the layering bug that TankService's
        *_as_related_action split was created to fix.

        Booking a 0.00 sale is worse than refusing one: the fuel leaves
        the tank either way, but a zero-value sale silently understates
        revenue everywhere downstream and looks like a completed,
        correct transaction.
        """
        if not FuelService._is_priced(fuel):
            raise ConflictError(
                f"{fuel.fuel_type} has no selling price set. "
                "A manager must set the price before this fuel can be sold."
            )

    def _get_fuel_or_raise(self, fuel_id: str) -> Fuel:
        fuel: Optional[Fuel] = self._fuel_repo.get_by_id(fuel_id)
        if not fuel:
            raise NotFoundError(f"Fuel type not found: {fuel_id}")
        return fuel
