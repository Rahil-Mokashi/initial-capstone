import uuid

from sqlalchemy import Column, Date, ForeignKey, String
from sqlalchemy.orm import relationship

from .base import Base, EntityMixin


class Employee(EntityMixin, Base):
    """HR master record for every attendant/employee (problemstatement.md #7, #10).

    Distinct from User: a User is a login account, an Employee is the HR
    record. Not every employee necessarily has login access, so user_id is
    nullable. Exit is tracked via exit_date/status, never by deleting the
    row — historical HR data must be preserved (CLAUDE.md).
    """

    __tablename__ = "employees"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_code = Column(String(32), unique=True, nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=True)
    role_id = Column(String(36), ForeignKey("roles.id"), nullable=True)

    first_name = Column(String(128), nullable=False)
    last_name = Column(String(128), nullable=False)
    contact_number = Column(String(32), nullable=False)
    email = Column(String(256), nullable=True)

    designation = Column(String(128), nullable=True)
    department = Column(String(128), nullable=True)
    assigned_outlet = Column(String(128), nullable=True, default="Main Outlet")

    joining_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=True)

    emergency_contact_name = Column(String(128), nullable=True)
    emergency_contact_phone = Column(String(32), nullable=True)

    user = relationship("User")
    role = relationship("Role")
    documents = relationship("EmployeeDocument", back_populates="employee")

    def __repr__(self) -> str:
        return f"<Employee(employee_code={self.employee_code!r}, status={self.status!r})>"
