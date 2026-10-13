"""Repositories for the credit-control tables (approvals, limit overrides, follow-ups, bill details)."""

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.credit_recovery import CreditBillDetail, CreditFollowUp, CreditLimitOverride, CustomerApproval
from app.repositories.base import safe_commit


class _Base:
    def __init__(self, session: Session):
        self._session = session

    def _add(self, row):
        self._session.add(row)
        safe_commit(self._session)
        self._session.refresh(row)
        return row

    def _save(self, row):
        safe_commit(self._session)
        self._session.refresh(row)
        return row


class CustomerApprovalRepository(_Base):
    def get_for_customer(self, customer_id: str) -> Optional[CustomerApproval]:
        return self._session.query(CustomerApproval).filter_by(customer_id=customer_id).first()

    def list_all(self) -> List[CustomerApproval]:
        return self._session.query(CustomerApproval).all()

    add = _Base._add
    save = _Base._save


class CreditOverrideRepository(_Base):
    add = _Base._add

    def list_for_customer(self, customer_id: str) -> List[CreditLimitOverride]:
        return (
            self._session.query(CreditLimitOverride)
            .filter_by(customer_id=customer_id)
            .order_by(CreditLimitOverride.created_at)
            .all()
        )

    def sale_ids(self) -> set:
        return {r[0] for r in self._session.query(CreditLimitOverride.sale_id).filter(CreditLimitOverride.sale_id.isnot(None))}

    def list_all(self) -> List[CreditLimitOverride]:
        return self._session.query(CreditLimitOverride).order_by(CreditLimitOverride.created_at.desc()).all()


class FollowUpRepository(_Base):
    add = _Base._add
    save = _Base._save

    def get(self, follow_up_id: str) -> Optional[CreditFollowUp]:
        return self._session.get(CreditFollowUp, follow_up_id)

    def list_for_customer(self, customer_id: str) -> List[CreditFollowUp]:
        return (
            self._session.query(CreditFollowUp)
            .filter_by(customer_id=customer_id)
            .order_by(CreditFollowUp.followed_on.desc(), CreditFollowUp.created_at.desc())
            .all()
        )

    def open_with_promise_on_or_before(self, day: date) -> List[CreditFollowUp]:
        return (
            self._session.query(CreditFollowUp)
            .filter(CreditFollowUp.status == "open", CreditFollowUp.promised_date.isnot(None), CreditFollowUp.promised_date <= day)
            .order_by(CreditFollowUp.promised_date)
            .all()
        )

    def open_for_customer(self, customer_id: str) -> List[CreditFollowUp]:
        return self._session.query(CreditFollowUp).filter_by(customer_id=customer_id, status="open").all()

    def last_contact(self) -> Dict[str, date]:
        out: Dict[str, date] = {}
        for cid, when in self._session.query(CreditFollowUp.customer_id, CreditFollowUp.followed_on).all():
            if cid not in out or when > out[cid]:
                out[cid] = when
        return out


class BillDetailRepository(_Base):
    def get_for_sale(self, sale_id: str) -> Optional[CreditBillDetail]:
        return self._session.query(CreditBillDetail).filter_by(sale_id=sale_id).first()

    def map_for_sales(self, sale_ids: List[str]) -> Dict[str, CreditBillDetail]:
        if not sale_ids:
            return {}
        rows = self._session.query(CreditBillDetail).filter(CreditBillDetail.sale_id.in_(sale_ids)).all()
        return {r.sale_id: r for r in rows}

    add = _Base._add
    save = _Base._save
