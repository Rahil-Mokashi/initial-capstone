from sqlalchemy.orm import Session
from app.models.tender import Tender
from app.repositories.base import safe_commit


class TenderRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, tender_id: str):
        return self._session.query(Tender).filter_by(id=tender_id, is_deleted=False).first()

    def get_by_name(self, name: str):
        return self._session.query(Tender).filter_by(name=name, is_deleted=False).first()

    def list_active(self):
        return self._session.query(Tender).filter_by(is_deleted=False, status="active").all()

    def add(self, tender: Tender):
        self._session.add(tender)
        safe_commit(self._session)
        self._session.refresh(tender)
        return tender

    def update(self, tender: Tender):
        safe_commit(self._session)
        self._session.refresh(tender)
        return tender
