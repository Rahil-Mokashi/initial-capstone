from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.credit_account import CreditAccount
from app.repositories.base import safe_commit


class CreditAccountRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, account_id: str) -> Optional[CreditAccount]:
        return self._session.query(CreditAccount).filter_by(id=account_id).first()

    def get_by_customer_id(self, customer_id: str) -> Optional[CreditAccount]:
        return self._session.query(CreditAccount).filter_by(customer_id=customer_id).first()

    def list_all(self) -> List[CreditAccount]:
        return self._session.query(CreditAccount).all()

    def add(self, account: CreditAccount) -> CreditAccount:
        self._session.add(account)
        safe_commit(self._session)
        self._session.refresh(account)
        return account

    def update(self, account: CreditAccount) -> CreditAccount:
        safe_commit(self._session)
        self._session.refresh(account)
        return account
