from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.expense import Expense, ExpenseCategory
from app.repositories.base import safe_commit


class ExpenseCategoryRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, category_id: str) -> Optional[ExpenseCategory]:
        return self._session.query(ExpenseCategory).filter_by(id=category_id).first()

    def get_by_name(self, name: str) -> Optional[ExpenseCategory]:
        return self._session.query(ExpenseCategory).filter_by(name=name).first()

    def list_all(self) -> List[ExpenseCategory]:
        return self._session.query(ExpenseCategory).all()

    def add(self, category: ExpenseCategory) -> ExpenseCategory:
        self._session.add(category)
        safe_commit(self._session)
        self._session.refresh(category)
        return category


class ExpenseRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, expense_id: str) -> Optional[Expense]:
        return self._session.query(Expense).filter_by(id=expense_id).first()

    def list_all(self) -> List[Expense]:
        return self._session.query(Expense).order_by(Expense.expense_date.desc()).all()

    def list_by_shift(self, shift_id: str) -> List[Expense]:
        return self._session.query(Expense).filter_by(shift_id=shift_id).all()

    def add(self, expense: Expense) -> Expense:
        self._session.add(expense)
        safe_commit(self._session)
        self._session.refresh(expense)
        return expense

    def update(self, expense: Expense) -> Expense:
        safe_commit(self._session)
        self._session.refresh(expense)
        return expense
