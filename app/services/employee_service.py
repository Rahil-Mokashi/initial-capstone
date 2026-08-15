"""
Employee / HR service layer (problemstatement.md #7, #10).

Owns employee master data, documents, and status/exit tracking. Every
create/update/status-change/exit/document event is written to the audit
trail. Employees are never hard-deleted — exit is recorded via status +
exit_date, matching the project's rule against destroying historical data.
"""

from datetime import date
from typing import List, Optional

from app.core.constants import EmployeeStatus, Permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.schemas.employee import EmployeeCreate, EmployeeUpdate


class EmployeeService:
    def __init__(self, employee_repo, document_repo, user_repo, role_repo, audit_repo, auth_service):
        self._employee_repo = employee_repo
        self._document_repo = document_repo
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    def _validate_references(self, role_id: Optional[str], user_id: Optional[str]) -> None:
        if role_id and not self._role_repo.get_by_id(role_id):
            raise NotFoundError(f"Role not found: {role_id}")
        if user_id:
            if not self._user_repo.get_by_id(user_id):
                raise NotFoundError(f"User not found: {user_id}")
            if any(e.user_id == user_id for e in self._employee_repo.list_all()):
                raise ConflictError(f"User {user_id} is already linked to another employee")

    @require_permission(Permission.EMPLOYEE_MANAGE.value)
    def create_employee(self, actor_user_id: str, data: EmployeeCreate) -> Employee:
        self._validate_references(data.role_id, data.user_id)

        employee = Employee(
            employee_code=self._employee_repo.next_employee_code(),
            first_name=data.first_name,
            last_name=data.last_name,
            contact_number=data.contact_number,
            email=data.email,
            designation=data.designation,
            department=data.department,
            assigned_outlet=data.assigned_outlet,
            joining_date=data.joining_date,
            role_id=data.role_id,
            user_id=data.user_id,
            emergency_contact_name=data.emergency_contact_name,
            emergency_contact_phone=data.emergency_contact_phone,
            status=EmployeeStatus.ACTIVE.value,
        )
        employee = self._employee_repo.add(employee)
        self._audit_repo.record(
            event_type="employee_created",
            actor_id=actor_user_id,
            entity_type="Employee",
            entity_id=employee.id,
            description=f"Created employee {employee.employee_code}",
            new_value=f"{employee.first_name} {employee.last_name}",
        )
        return employee

    @require_permission(Permission.EMPLOYEE_MANAGE.value)
    def update_employee(self, actor_user_id: str, employee_id: str, data: EmployeeUpdate) -> Employee:
        employee = self._get_or_raise(employee_id)
        if data.role_id:
            self._validate_references(data.role_id, None)

        old_snapshot = f"{employee.first_name} {employee.last_name} / {employee.designation}"
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(employee, field, value)

        employee = self._employee_repo.update(employee)
        self._audit_repo.record(
            event_type="employee_updated",
            actor_id=actor_user_id,
            entity_type="Employee",
            entity_id=employee.id,
            old_value=old_snapshot,
            new_value=f"{employee.first_name} {employee.last_name} / {employee.designation}",
        )
        return employee

    @require_permission(Permission.EMPLOYEE_MANAGE.value)
    def change_status(
        self, actor_user_id: str, employee_id: str, new_status: EmployeeStatus, reason: str
    ) -> Employee:
        employee = self._get_or_raise(employee_id)
        old_status = employee.status
        employee.status = new_status.value
        employee = self._employee_repo.update(employee)
        self._audit_repo.record(
            event_type="employee_status_changed",
            actor_id=actor_user_id,
            entity_type="Employee",
            entity_id=employee.id,
            description=reason,
            old_value=old_status,
            new_value=new_status.value,
        )
        return employee

    @require_permission(Permission.EMPLOYEE_MANAGE.value)
    def record_exit(self, actor_user_id: str, employee_id: str, exit_date: date, reason: str) -> Employee:
        employee = self._get_or_raise(employee_id)
        if exit_date < employee.joining_date:
            raise ValueError("exit_date cannot be before joining_date")

        old_status = employee.status
        employee.exit_date = exit_date
        employee.status = EmployeeStatus.TERMINATED.value
        employee = self._employee_repo.update(employee)
        self._audit_repo.record(
            event_type="employee_exit",
            actor_id=actor_user_id,
            entity_type="Employee",
            entity_id=employee.id,
            description=reason,
            old_value=old_status,
            new_value=EmployeeStatus.TERMINATED.value,
        )
        return employee

    @require_permission(Permission.EMPLOYEE_MANAGE.value)
    def add_document(
        self,
        actor_user_id: str,
        employee_id: str,
        document_type: str,
        file_reference: str,
        description: Optional[str] = None,
    ) -> EmployeeDocument:
        self._get_or_raise(employee_id)
        document = EmployeeDocument(
            employee_id=employee_id,
            document_type=document_type,
            file_reference=file_reference,
            description=description,
        )
        document = self._document_repo.add(document)
        self._audit_repo.record(
            event_type="employee_document_added",
            actor_id=actor_user_id,
            entity_type="EmployeeDocument",
            entity_id=document.id,
            description=f"Added {document_type} for employee {employee_id}",
        )
        return document

    @require_permission(Permission.EMPLOYEE_MANAGE.value)
    def remove_document(self, actor_user_id: str, document_id: str, reason: str) -> EmployeeDocument:
        document = self._document_repo.get_by_id(document_id)
        if not document:
            raise NotFoundError(f"Document not found: {document_id}")
        document.is_deleted = True
        document = self._document_repo.update(document)
        self._audit_repo.record(
            event_type="employee_document_removed",
            actor_id=actor_user_id,
            entity_type="EmployeeDocument",
            entity_id=document.id,
            description=reason,
        )
        return document

    @require_permission(Permission.EMPLOYEE_VIEW.value)
    def get_employee(self, actor_user_id: str, employee_id: str) -> Employee:
        return self._get_or_raise(employee_id)

    @require_permission(Permission.EMPLOYEE_VIEW.value)
    def list_employees(self, actor_user_id: str) -> List[Employee]:
        return self._employee_repo.list_all()

    def _get_or_raise(self, employee_id: str) -> Employee:
        employee = self._employee_repo.get_by_id(employee_id)
        if not employee:
            raise NotFoundError(f"Employee not found: {employee_id}")
        return employee
