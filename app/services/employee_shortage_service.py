"""Employee cash shortage and its recovery (docs/daily-report-spec.md
section 4; A2 in PROJECT_CONTEXT.md's working assumptions - Step 5 of
the settlement-side build).

A cash shortage found at shift reconciliation is booked as an Expense
the moment it's found, so the books balance immediately, and
simultaneously tracked as a receivable against the employee named
responsible for it - not written off, not silently absorbed, cleared
later by one or more cash repayments. Naming the responsible employee
is a human judgement call made at the point of recording, never derived
automatically from the reconciliation itself.
"""

from decimal import Decimal
from typing import List

from app.core.constants import (
    CASH_SHORTAGE_EXPENSE_CATEGORY_NAME,
    PaymentMethod,
    Permission,
    TenderSettlementType,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.employee_cash_shortage import EmployeeCashShortage, EmployeeShortageRecovery
from app.repositories.base import session_for, unit_of_work
from app.schemas.employee_cash_shortage import EmployeeCashShortageRecord, EmployeeShortageRecoveryRecord
from app.schemas.expense import ExpenseCreate


class EmployeeShortageService:
    def __init__(
        self,
        shortage_repo,
        recovery_repo,
        reconciliation_line_repo,
        employee_repo,
        category_repo,
        expense_service,
        audit_repo,
        auth_service,
        cash_book_repo,
    ):
        self._shortage_repo = shortage_repo
        self._recovery_repo = recovery_repo
        self._reconciliation_line_repo = reconciliation_line_repo
        self._employee_repo = employee_repo
        self._category_repo = category_repo
        self._expense_service = expense_service
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        # A recovery is a real cash receipt into whichever shift's cash
        # book the employee actually repaid during (see
        # EmployeeShortageRecovery's own docstring and record_recovery
        # below) - required, not optional, since a recovery with nowhere
        # to land would silently understate that shift's cash-in-hand.
        self._cash_book_repo = cash_book_repo
        self._session = session_for(shortage_repo)

    # A dedicated permission pair, not a reuse of RECONCILIATION_MANAGE -
    # see Permission.SHORTAGE_MANAGE's own comment in app/core/
    # constants.py: this is a receivable lifecycle, the same kind of
    # thing CreditAccount/CustomerPayment already is under CREDIT_MANAGE.
    @require_permission(Permission.SHORTAGE_MANAGE.value)
    def record_shortage(self, actor_user_id: str, data: EmployeeCashShortageRecord) -> EmployeeCashShortage:
        with unit_of_work(self._session):
            return self._record_shortage_impl(actor_user_id, data)

    def _record_shortage_impl(self, actor_user_id: str, data: EmployeeCashShortageRecord) -> EmployeeCashShortage:
        line = self._reconciliation_line_repo.get_by_id(data.shift_reconciliation_line_id)
        if not line:
            raise NotFoundError(f"Shift reconciliation line not found: {data.shift_reconciliation_line_id}")
        if not line.tender or line.tender.settlement_type != TenderSettlementType.IMMEDIATE_CASH.value:
            raise ValueError(
                "Only a variance on an immediate-cash tender (e.g. Cash) can be booked as an employee cash shortage"
            )
        if line.variance >= 0:
            raise ValueError("This reconciliation line has no shortage to book - its variance is not negative")
        if self._shortage_repo.get_by_line_id(line.id):
            raise ConflictError("A cash shortage has already been recorded for this reconciliation line")

        employee = self._employee_repo.get_by_id(data.employee_id)
        if not employee:
            raise NotFoundError(f"Employee not found: {data.employee_id}")

        category = self._category_repo.get_by_name(CASH_SHORTAGE_EXPENSE_CATEGORY_NAME)
        if not category:
            raise ConflictError(
                f"The seeded {CASH_SHORTAGE_EXPENSE_CATEGORY_NAME!r} expense category is missing - "
                "run app.database.seed.seed_initial_data()"
            )

        # Always the line's own variance, never re-typed (A4's "computed,
        # not re-typed" rule applied here too).
        amount = abs(line.variance)

        expense = self._expense_service.create_expense_as_related_action(
            actor_user_id,
            ExpenseCreate(
                category_id=category.id,
                amount=amount,
                payment_method=PaymentMethod.CASH,
                employee_id=data.employee_id,
                shift_id=line.shift_reconciliation.shift_id,
                description=(
                    f"Cash shortage recorded at reconciliation of "
                    f"{line.shift_reconciliation.shift.shift_date if line.shift_reconciliation.shift else ''} "
                    f"({line.tender.name})"
                ),
            ),
        )

        shortage = EmployeeCashShortage(
            shift_reconciliation_line_id=line.id,
            employee_id=data.employee_id,
            expense_id=expense.id,
            amount=amount,
            notes=data.notes,
            recorded_by_id=actor_user_id,
        )
        shortage = self._shortage_repo.add(shortage)

        self._audit_repo.record(
            event_type="employee_cash_shortage_recorded",
            actor_id=actor_user_id,
            entity_type="EmployeeCashShortage",
            entity_id=shortage.id,
            description=f"{employee.first_name} {employee.last_name} short by {amount:.2f}",
        )
        return shortage

    @require_permission(Permission.SHORTAGE_VIEW.value)
    def list_all(self, actor_user_id: str) -> List[EmployeeCashShortage]:
        return self._shortage_repo.list_all()

    @require_permission(Permission.SHORTAGE_VIEW.value)
    def list_unbooked_shortage_lines(self, actor_user_id: str):
        return self._reconciliation_line_repo.list_unbooked_shortage_candidates()

    @require_permission(Permission.SHORTAGE_VIEW.value)
    def list_for_employee(self, actor_user_id: str, employee_id: str) -> List[EmployeeCashShortage]:
        return self._shortage_repo.list_for_employee(employee_id)

    @require_permission(Permission.SHORTAGE_MANAGE.value)
    def record_recovery(
        self, actor_user_id: str, data: EmployeeShortageRecoveryRecord
    ) -> EmployeeShortageRecovery:
        with unit_of_work(self._session):
            return self._record_recovery_impl(actor_user_id, data)

    def _record_recovery_impl(
        self, actor_user_id: str, data: EmployeeShortageRecoveryRecord
    ) -> EmployeeShortageRecovery:
        shortage = self._get_shortage_or_raise(data.employee_cash_shortage_id)

        # The physical cash lands in whichever shift's cash book the
        # repayment happens during - it must already exist (mirrors
        # ShiftBankDeposit's own requirement in ShiftCashBookService.
        # record_bank_deposit: "record advance/final first"), since a
        # recovery has nowhere real to post to otherwise.
        cash_book = self._cash_book_repo.get_by_shift_id(data.shift_id)
        if not cash_book:
            raise NotFoundError(
                f"No cash book recorded for shift {data.shift_id} yet - record advance/final first"
            )

        recovery = EmployeeShortageRecovery(
            employee_cash_shortage_id=shortage.id,
            shift_cash_book_id=cash_book.id,
            amount=data.amount,
            notes=data.notes,
            recorded_by_id=actor_user_id,
        )
        recovery = self._recovery_repo.add(recovery)

        self._audit_repo.record(
            event_type="employee_shortage_recovery_recorded",
            actor_id=actor_user_id,
            entity_type="EmployeeShortageRecovery",
            entity_id=recovery.id,
            description=f"Recovered {data.amount:.2f} against shortage {shortage.id}",
        )
        return recovery

    @require_permission(Permission.SHORTAGE_VIEW.value)
    def get_outstanding_balance(self, actor_user_id: str, shortage_id: str) -> Decimal:
        return self._compute_outstanding_balance(shortage_id)

    def _compute_outstanding_balance(self, shortage_id: str) -> Decimal:
        shortage = self._get_shortage_or_raise(shortage_id)
        recovered = sum(
            (r.amount for r in self._recovery_repo.list_for_shortage(shortage_id)), Decimal("0")
        )
        return shortage.amount - recovered

    def _get_shortage_or_raise(self, shortage_id: str) -> EmployeeCashShortage:
        shortage = self._shortage_repo.get_by_id(shortage_id)
        if not shortage:
            raise NotFoundError(f"Employee cash shortage not found: {shortage_id}")
        return shortage
