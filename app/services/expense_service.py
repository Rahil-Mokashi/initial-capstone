"""Expense management (problemstatement.md #22, Phase 14).

Expenses are never deleted or edited once recorded - approve/reject are
the only forward transitions, both requiring the stricter
EXPENSE_APPROVE permission (not granted to Accountant, the same
"a stricter permission for a sensitive action" pattern already used for
Shift.reopen_shift's SHIFT_REOPEN). A correction to an approved/rejected
expense is a new expense record, matching the project's
VOID/REVERSE/ADJUST-not-DELETE rule for financial records.
"""

from datetime import date, datetime, timezone
from typing import List

from app.core.constants import ExpenseStatus, Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.models.expense import Expense, ExpenseCategory
from app.schemas.expense import ExpenseCategoryCreate, ExpenseCreate


class ExpenseService:
    def __init__(self, expense_repo, category_repo, employee_repo, shift_repo, audit_repo, auth_service):
        self._expense_repo = expense_repo
        self._category_repo = category_repo
        self._employee_repo = employee_repo
        self._shift_repo = shift_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    @require_permission(Permission.EXPENSE_MANAGE.value)
    def create_category(self, actor_user_id: str, data: ExpenseCategoryCreate) -> ExpenseCategory:
        if self._category_repo.get_by_name(data.name):
            raise ConflictError(f"An expense category named {data.name!r} already exists")

        category = ExpenseCategory(name=data.name, status=StatusEnum.ACTIVE.value)
        category = self._category_repo.add(category)
        self._audit_repo.record(
            event_type="expense_category_created",
            actor_id=actor_user_id,
            entity_type="ExpenseCategory",
            entity_id=category.id,
            description=f"Created expense category {data.name}",
        )
        return category

    @require_permission(Permission.EXPENSE_VIEW.value)
    def list_categories(self, actor_user_id: str) -> List[ExpenseCategory]:
        return self._category_repo.list_all()

    @require_permission(Permission.EXPENSE_MANAGE.value)
    def create_expense(self, actor_user_id: str, data: ExpenseCreate) -> Expense:
        category = self._category_repo.get_by_id(data.category_id)
        if not category:
            raise NotFoundError(f"Expense category not found: {data.category_id}")
        if category.status != StatusEnum.ACTIVE.value:
            raise ConflictError(f"Expense category {category.name} is not active")

        if not self._employee_repo.get_by_id(data.employee_id):
            raise NotFoundError(f"Employee not found: {data.employee_id}")
        if data.shift_id and not self._shift_repo.get_by_id(data.shift_id):
            raise NotFoundError(f"Shift not found: {data.shift_id}")

        expense = Expense(
            category_id=data.category_id,
            amount=data.amount,
            expense_date=date.today(),
            payment_method=data.payment_method.value,
            receipt_reference=data.receipt_reference,
            description=data.description,
            employee_id=data.employee_id,
            shift_id=data.shift_id,
            status=ExpenseStatus.PENDING.value,
            recorded_by_id=actor_user_id,
        )
        expense = self._expense_repo.add(expense)
        self._audit_repo.record(
            event_type="expense_recorded",
            actor_id=actor_user_id,
            entity_type="Expense",
            entity_id=expense.id,
            description=f"Recorded {data.amount} expense in {category.name}",
        )
        return expense

    @require_permission(Permission.EXPENSE_VIEW.value)
    def list_expenses(self, actor_user_id: str) -> List[Expense]:
        return self._expense_repo.list_all()

    @require_permission(Permission.EXPENSE_APPROVE.value)
    def approve_expense(self, actor_user_id: str, expense_id: str, remarks: str = "") -> Expense:
        expense = self._get_expense_or_raise(expense_id)
        if expense.status != ExpenseStatus.PENDING.value:
            raise ConflictError(f"Cannot approve an expense with status {expense.status}")

        expense.status = ExpenseStatus.APPROVED.value
        expense.approved_by_id = actor_user_id
        expense.approved_at = datetime.now(timezone.utc)
        expense.approval_remarks = remarks.strip() or None
        expense = self._expense_repo.update(expense)

        self._audit_repo.record(
            event_type="expense_approved",
            actor_id=actor_user_id,
            entity_type="Expense",
            entity_id=expense.id,
            description=remarks.strip() or "Approved",
        )
        return expense

    @require_permission(Permission.EXPENSE_APPROVE.value)
    def reject_expense(self, actor_user_id: str, expense_id: str, reason: str) -> Expense:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to reject an expense")

        expense = self._get_expense_or_raise(expense_id)
        if expense.status != ExpenseStatus.PENDING.value:
            raise ConflictError(f"Cannot reject an expense with status {expense.status}")

        expense.status = ExpenseStatus.REJECTED.value
        expense.approved_by_id = actor_user_id
        expense.approval_remarks = reason.strip()
        expense = self._expense_repo.update(expense)

        self._audit_repo.record(
            event_type="expense_rejected",
            actor_id=actor_user_id,
            entity_type="Expense",
            entity_id=expense.id,
            description=reason.strip(),
        )
        return expense

    def _get_expense_or_raise(self, expense_id: str) -> Expense:
        expense = self._expense_repo.get_by_id(expense_id)
        if not expense:
            raise NotFoundError(f"Expense not found: {expense_id}")
        return expense
