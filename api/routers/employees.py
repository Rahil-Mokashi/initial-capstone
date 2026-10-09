"""Employees (HR master data). Same EmployeeService calls as app/ui/employee_window.py."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, Out, Reason
from api.services import Services
from app.core.constants import EmployeeStatus
from app.schemas.employee import EmployeeCreate, EmployeeUpdate

router = APIRouter(tags=["employees"])


class EmployeeFull(Out):
    id: str
    employee_code: str
    first_name: str
    last_name: str
    contact_number: str
    email: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    assigned_outlet: Optional[str] = None
    joining_date: date
    exit_date: Optional[date] = None
    status: str
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class DocumentOut(Out):
    id: str
    employee_id: str
    document_type: str
    file_reference: str
    description: Optional[str] = None


class EmployeeCreateIn(In):
    first_name: str
    last_name: str
    contact_number: str
    joining_date: date
    email: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    assigned_outlet: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class EmployeeUpdateIn(In):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    assigned_outlet: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class StatusIn(In):
    status: EmployeeStatus
    reason: Reason


class ExitIn(In):
    # The Qt screen always uses today's date; an explicit date is accepted for back-dated exits.
    exit_date: Optional[date] = None
    reason: Reason


class DocumentIn(In):
    document_type: Reason
    file_reference: Reason
    description: Optional[str] = None


class RemoveDocumentIn(In):
    reason: Reason


@router.get("/employees", response_model=list[EmployeeFull])
def list_employees(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.employees.list_employees(user.id)


@router.post("/employees", response_model=EmployeeFull, status_code=201)
def create_employee(body: EmployeeCreateIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.employees.create_employee(user.id, EmployeeCreate(**body.model_dump()))


@router.get("/employees/{employee_id}", response_model=EmployeeFull)
def get_employee(employee_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.employees.get_employee(user.id, employee_id)


@router.patch("/employees/{employee_id}", response_model=EmployeeFull)
def update_employee(
    employee_id: str, body: EmployeeUpdateIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    # Only the fields that were sent are changed (EmployeeUpdate uses exclude_unset).
    return services.employees.update_employee(user.id, employee_id, EmployeeUpdate(**body.model_dump(exclude_unset=True)))


@router.post("/employees/{employee_id}/status", response_model=EmployeeFull)
def change_status(
    employee_id: str, body: StatusIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return services.employees.change_status(user.id, employee_id, body.status, body.reason)


@router.post("/employees/{employee_id}/exit", response_model=EmployeeFull)
def record_exit(employee_id: str, body: ExitIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.employees.record_exit(user.id, employee_id, body.exit_date or date.today(), body.reason)


@router.get("/employees/{employee_id}/documents", response_model=list[DocumentOut])
def list_documents(employee_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.employees.list_documents(user.id, employee_id)


@router.post("/employees/{employee_id}/documents", response_model=DocumentOut, status_code=201)
def add_document(
    employee_id: str, body: DocumentIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return services.employees.add_document(user.id, employee_id, body.document_type, body.file_reference, body.description)


@router.post("/employees/documents/{document_id}/remove", response_model=DocumentOut)
def remove_document(
    document_id: str, body: RemoveDocumentIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
):
    return services.employees.remove_document(user.id, document_id, body.reason)
