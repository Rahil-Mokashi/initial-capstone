import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class EmployeeDocument(Base):
    """A document reference attached to an employee (ID proof, photo, etc.).

    Removal is a soft delete (is_deleted), never a hard delete, so document
    history survives corrections — consistent with the project's rule
    against silently destroying historical records.
    """

    __tablename__ = "employee_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)
    document_type = Column(String(64), nullable=False)
    file_reference = Column(String(512), nullable=False)
    description = Column(String(256), nullable=True)
    uploaded_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)

    employee = relationship("Employee", back_populates="documents")

    def __repr__(self) -> str:
        return f"<EmployeeDocument(employee_id={self.employee_id!r}, document_type={self.document_type!r})>"
