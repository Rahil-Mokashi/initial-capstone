"""Expenses and expense categories. Same ExpenseService calls as app/ui/expense_window.py."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out
from api.services import Services
from app.core.constants import PaymentMethod
from app.schemas.expense import ExpenseCategoryCreate, ExpenseCreate

router = APIRouter(tags=["expenses"])


class ExpenseOut(Out):
    id: str
    expense_date: date
    category_id: str
    category: Optional[str] = None
    amount: MoneyOut
    payment_method: str
    employee_id: str
    employee: Optional[str] = None
    receipt_reference: Optional[str] = None
    description: Optional[str] = None
    status: str


class CategoryOut(Out):
    id: str
    name: str
    status: str


class IdLabel(Out):
    id: str
    label: str


class ExpenseOptions(Out):
    """The Record Expense dialog's dropdowns: active categories, every employee, open shifts."""

    categories: list[IdLabel]
    employees: list[IdLabel]
    shifts: list[IdLabel]


class ExpenseIn(In):
    category_id: str
    amount: MoneyIn
    payment_method: PaymentMethod
    employee_id: str
    shift_id: Optional[str] = None
    receipt_reference: Optional[str] = None
    description: Optional[str] = None


class CategoryIn(In):
    name: str


class ApproveIn(In):
    remarks: str = ""


class RejectIn(In):
    reason: OptionalReason


def expense_out(e) -> ExpenseOut:
    emp = e.employee
    return ExpenseOut(
        id=e.id,
        expense_date=e.expense_date,
        category_id=e.category_id,
        category=e.category.name if e.category else None,
        amount=e.amount,
        payment_method=e.payment_method,
        employee_id=e.employee_id,
        employee=f"{emp.first_name} {emp.last_name}" if emp else None,
        receipt_reference=e.receipt_reference,
        description=e.description,
        status=e.status,
    )


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [expense_out(e) for e in services.expenses.list_expenses(user.id)]


@router.get("/expenses/options", response_model=ExpenseOptions)
def expense_options(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return ExpenseOptions(
        categories=[IdLabel(id=c.id, label=c.name) for c in services.expenses.list_categories(user.id) if c.status == "active"],
        employees=[
            IdLabel(id=e.id, label=f"{e.employee_code} - {e.first_name} {e.last_name}")
            for e in services.employees.list_employees(user.id)
        ],
        shifts=[
            IdLabel(id=s.id, label=f"{s.shift_date} {s.shift_label}") for s in services.shifts.list_shifts(user.id) if s.status == "open"
        ],
    )


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return expense_out(services.expenses.create_expense(user.id, ExpenseCreate(**body.model_dump())))


@router.post("/expenses/{expense_id}/approve", response_model=ExpenseOut)
def approve_expense(expense_id: str, body: ApproveIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return expense_out(services.expenses.approve_expense(user.id, expense_id, body.remarks.strip()))


@router.post("/expenses/{expense_id}/reject", response_model=ExpenseOut)
def reject_expense(expense_id: str, body: RejectIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return expense_out(services.expenses.reject_expense(user.id, expense_id, body.reason))


@router.get("/expense-categories", response_model=list[CategoryOut])
def list_categories(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.expenses.list_categories(user.id)


@router.post("/expense-categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.expenses.create_category(user.id, ExpenseCategoryCreate(name=body.name))
