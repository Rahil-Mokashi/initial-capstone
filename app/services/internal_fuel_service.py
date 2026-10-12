"""Internal fuel use (own vehicle, genset, Omni): recorded the way the owner's report does it.

An EXPENSE at selling price with the litres and vehicle written on it. It is deliberately NOT also
deducted from tank stock: that fuel already passed through the nozzle meters, so deducting it again
would double count (the trap TESTING fell into). Setting `internal_fuel_deducts_tank` (T-12) records
the owner's answer; it is off, and while it is off this service never touches a tank.
"""

from decimal import Decimal

from app.core.constants import Permission, PaymentMethod
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import money, volume
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.models.expense import ExpenseCategory
from app.models.internal_fuel_use import InternalFuelUse
from app.repositories.base import session_for, unit_of_work
from app.schemas.expense import ExpenseCreate

INTERNAL_FUEL_CATEGORY = "Internal fuel use"


class InternalFuelService:
    def __init__(self, use_repo, category_repo, fuel_repo, expense_service, settings, audit_repo, auth_service):
        self._uses = use_repo
        self._categories = category_repo
        self._fuels = fuel_repo
        self._expenses = expense_service
        self._settings = settings
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(use_repo)

    @require_permission(Permission.EXPENSE_MANAGE.value)
    def record(self, actor_user_id: str, shift_id: str, employee_id: str, fuel_id: str, litres: Decimal, vehicle: str) -> InternalFuelUse:
        vehicle = (vehicle or "").strip()
        if not vehicle:
            raise ValueError("Write which vehicle or machine the fuel went into")
        litres = volume(litres)
        if litres <= 0:
            raise ValueError("The litres must be more than zero")
        if self._settings.get("internal_fuel_deducts_tank") == "on":
            raise ConflictError(
                "Deducting internal fuel from tank stock is switched on (T-12) but is not built yet; "
                "switch it off in settings to record internal fuel the way the report does."
            )
        fuel = self._fuels.get_by_id(fuel_id)
        if fuel is None:
            raise NotFoundError(f"Fuel not found: {fuel_id}")
        rate = money(fuel.rate_per_liter)
        if rate <= 0:
            raise ConflictError(f"{fuel.fuel_type} has no selling price set, so the expense cannot be valued")
        with unit_of_work(self._session):
            category = self._categories.get_by_name(INTERNAL_FUEL_CATEGORY)
            if category is None:
                category = self._categories.add(ExpenseCategory(name=INTERNAL_FUEL_CATEGORY, status=StatusEnum.ACTIVE.value))
            expense = self._expenses.create_expense(actor_user_id, ExpenseCreate(
                category_id=category.id, amount=money(litres * rate), payment_method=PaymentMethod.CASH,
                employee_id=employee_id, shift_id=shift_id,
                description=f"{fuel.fuel_type} Exp ({vehicle}) {litres.normalize():f} Lit",
            ))
            use = self._uses.add(InternalFuelUse(
                expense_id=expense.id, fuel_id=fuel_id, litres=litres, rate=rate, vehicle=vehicle,
            ))
            self._audit_repo.record(
                event_type="internal_fuel_use_recorded", actor_id=actor_user_id, entity_type="InternalFuelUse",
                entity_id=use.id, description=f"{litres} L of {fuel.fuel_type} for {vehicle} = {expense.amount} (tank stock not touched)",
            )
            return use
