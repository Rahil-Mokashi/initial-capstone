from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.employee_document import EmployeeDocument


class EmployeeDocumentRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, document_id: str) -> Optional[EmployeeDocument]:
        return self._session.query(EmployeeDocument).filter_by(id=document_id, is_deleted=False).first()

    def list_for_employee(self, employee_id: str) -> List[EmployeeDocument]:
        return (
            self._session.query(EmployeeDocument)
            .filter_by(employee_id=employee_id, is_deleted=False)
            .all()
        )

    def add(self, document: EmployeeDocument) -> EmployeeDocument:
        self._session.add(document)
        self._session.commit()
        self._session.refresh(document)
        return document

    def update(self, document: EmployeeDocument) -> EmployeeDocument:
        self._session.commit()
        self._session.refresh(document)
        return document
