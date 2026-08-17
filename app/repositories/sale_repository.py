from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sale import Sale
from app.repositories.base import safe_commit


class SaleRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, sale_id: str) -> Optional[Sale]:
        return self._session.query(Sale).filter_by(id=sale_id).first()

    def list_all(self, limit: Optional[int] = None, offset: int = 0) -> List[Sale]:
        """Newest first, optionally one page at a time.

        limit defaults to None (everything) so existing callers and the
        reporting code are unchanged, but the UI passes a page size. At
        300 sales a day a pump reaches ~110,000 rows in a year, and
        loading all of them to show thirty is the difference between a
        screen that opens instantly in year three and one that does not.

        Ordering is by Sale.sale_at descending, which is also the column the
        page boundary is taken on, so pages cannot interleave.
        """
        query = self._session.query(Sale).order_by(Sale.sale_at.desc())
        if offset:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count_all(self) -> int:
        """Row count for the pager, computed by the database rather than
        by loading the rows and calling len()."""
        return self._session.query(func.count(Sale.id)).scalar() or 0

    def list_by_shift(self, shift_id: str) -> List[Sale]:
        return self._session.query(Sale).filter_by(shift_id=shift_id).order_by(Sale.sale_at.desc()).all()

    def list_by_nozzle(self, nozzle_id: str) -> List[Sale]:
        return self._session.query(Sale).filter_by(nozzle_id=nozzle_id).order_by(Sale.sale_at.desc()).all()

    def list_by_customer(self, customer_id: str) -> List[Sale]:
        return self._session.query(Sale).filter_by(customer_id=customer_id).order_by(Sale.sale_at.desc()).all()

    def next_receipt_number(self) -> str:
        """Sequential RCPT-000001, RCPT-000002, ...

        Derived from the highest receipt number ever issued, NOT from a
        row count. A count is not a high-water mark, and the two diverge
        the moment any row disappears - at which point COUNT(*) + 1
        returns a number that already exists, the unique index on
        receipt_number rejects the insert, and every further sale is
        blocked with an error an attendant cannot resolve.

        That is not hypothetical here, because this app ships a restore
        feature: restoring to an earlier backup rewinds the count while
        the receipt numbers already printed on customers' receipts stay
        issued. MAX() rewinds with the data, so the sequence continues
        from wherever the restored database actually left off.

        The read and the subsequent insert happen inside the caller's
        unit of work (see app/repositories/base.py), and SQLite permits
        only one writer at a time, so no second writer can claim the same
        number in between.
        """
        highest = self._session.query(func.max(Sale.receipt_number)).scalar()
        if not highest:
            return "RCPT-000001"
        try:
            last = int(str(highest).rsplit("-", 1)[1])
        except (IndexError, ValueError):
            # A receipt number that doesn't match the expected shape (a
            # hand-edited row, or a future format change) must not wedge
            # sales entirely - fall back to the row count, which is at
            # worst wrong in the same way the old implementation always was.
            last = self._session.query(func.count(Sale.id)).scalar() or 0
        return f"RCPT-{last + 1:06d}"

    def add(self, sale: Sale) -> Sale:
        self._session.add(sale)
        safe_commit(self._session)
        self._session.refresh(sale)
        return sale

    def update(self, sale: Sale) -> Sale:
        safe_commit(self._session)
        self._session.refresh(sale)
        return sale
