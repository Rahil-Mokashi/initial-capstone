"""The records the top-bar search can find, for the signed-in person only.

Thin: each list comes from the service that owns it, which checks the permission; a list the person may not read is simply left out,
so the search can never show something the sidebar would hide. The matching itself (typos, synonyms) is in the web app.
"""

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import Out
from api.services import Services
from app.core.constants import Permission
from app.database.base import StatusEnum

router = APIRouter(tags=["search"])


class RecordOut(Out):
    kind: str  # Employee | User | Customer | Vehicle | Nozzle | Dispenser | Tank | Supplier
    label: str
    hint: str = ""
    to: str


@router.get("/search/records", response_model=list[RecordOut])
def records(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    can = lambda p: services.auth.check_permission(user.id, p.value)  # noqa: E731
    out: list[RecordOut] = []
    if can(Permission.EMPLOYEE_VIEW):
        for e in services.employees.list_employees(user.id):
            out.append(RecordOut(kind="Employee", label=f"{e.first_name} {e.last_name}", hint=e.employee_code, to=f"/employees/{e.id}"))
    if can(Permission.USER_MANAGE):
        for u in services.users.list_users(user.id):
            out.append(RecordOut(kind="User", label=u.username, hint=f"{u.first_name} {u.last_name}".strip(), to=f"/users/{u.id}"))
    customers = {}
    if can(Permission.CREDIT_VIEW) and can(Permission.SALE_VIEW):  # customers and their vehicles open on the Credit screens
        for c in services.sales.list_customers(user.id):
            customers[c.id] = c.name
            if c.status == StatusEnum.ACTIVE.value:
                out.append(RecordOut(kind="Customer", label=c.name, hint=c.phone or "", to=f"/credit/customers/{c.id}"))
        for vehicle, customer_id in services.sales.list_vehicles(user.id):
            out.append(RecordOut(kind="Vehicle", label=vehicle, hint=customers.get(customer_id, ""), to=f"/credit/customers/{customer_id}" if customer_id else "/sales"))
    if can(Permission.NOZZLE_VIEW):
        for d in services.nozzles.list_dispensers(user.id):
            out.append(RecordOut(kind="Dispenser", label=f"Dispenser {d.code}", to="/nozzles"))
        for n in services.nozzles.list_nozzles(user.id):
            out.append(RecordOut(kind="Nozzle", label=f"Nozzle {n.code}", hint=n.dispenser.code if n.dispenser else "", to="/nozzles"))
    if can(Permission.INVENTORY_VIEW):
        for t in services.tanks.list_tanks(user.id):
            out.append(RecordOut(kind="Tank", label=f"Tank {t.code}", hint=t.fuel.fuel_type if t.fuel else "", to=f"/tanks/{t.id}"))
    if can(Permission.PROCUREMENT_VIEW):
        for s in services.procurement.list_suppliers(user.id):
            out.append(RecordOut(kind="Supplier", label=s.name, to="/procurement?tab=suppliers"))
    return out
