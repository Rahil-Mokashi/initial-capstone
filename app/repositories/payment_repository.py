from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.payment import Payment
from app.repositories.base import safe_commit


class PaymentRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, payment_id: str) -> Optional[Payment]:
        return self._session.query(Payment).filter_by(id=payment_id).first()

    def get_by_sale_id(self, sale_id: str) -> Optional[Payment]:
        return self._session.query(Payment).filter_by(sale_id=sale_id).first()

    def list_all(self, limit: Optional[int] = None, offset: int = 0) -> List[Payment]:
        """Newest first, optionally one page at a time.

        limit defaults to None (everything) so existing callers and the
        reporting code are unchanged, but the UI passes a page size. At
        300 sales a day a pump reaches ~110,000 rows in a year, and
        loading all of them to show thirty is the difference between a
        screen that opens instantly in year three and one that does not.

        Ordering is by Payment.payment_at descending, which is also the column the
        page boundary is taken on, so pages cannot interleave.
        """
        query = self._session.query(Payment).order_by(Payment.payment_at.desc())
        if offset:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count_all(self) -> int:
        """Row count for the pager, computed by the database rather than
        by loading the rows and calling len()."""
        return self._session.query(func.count(Payment.id)).scalar() or 0

    def add(self, payment: Payment) -> Payment:
        self._session.add(payment)
        safe_commit(self._session)
        self._session.refresh(payment)
        return payment

    def update(self, payment: Payment) -> Payment:
        safe_commit(self._session)
        self._session.refresh(payment)
        return payment
