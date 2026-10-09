"""Builds the service objects for ONE request.

Wiring mirrors AppController (app/ui/main_window.py): same repositories,
same constructor arguments. The only difference is lifetime: the Qt app
shares one long-lived Session on its UI thread; a threaded HTTP server must
not, so every request gets its own Session and its own services.
"""

from functools import cached_property

from sqlalchemy.orm import Session

from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.tank_service import TankService
from app.services.user_service import UserService


class Services:
    def __init__(self, db: Session, session_timeout_hours: int):
        self.db = db
        self._timeout = session_timeout_hours

    @cached_property
    def audit_repo(self) -> AuditLogRepository:
        return AuditLogRepository(self.db)

    @cached_property
    def user_repo(self) -> UserRepository:
        return UserRepository(self.db)

    @cached_property
    def employee_repo(self) -> EmployeeRepository:
        return EmployeeRepository(self.db)

    @cached_property
    def fuel_repo(self) -> FuelRepository:
        return FuelRepository(self.db)

    @cached_property
    def auth(self) -> AuthService:
        return AuthService(
            self.user_repo,
            self.audit_repo,
            UserSessionRepository(self.db),
            session_timeout_hours=self._timeout,
        )

    @cached_property
    def users(self) -> UserService:
        return UserService(self.user_repo, RoleRepository(self.db), self.audit_repo, self.auth)

    @cached_property
    def employees(self) -> EmployeeService:
        return EmployeeService(
            self.employee_repo,
            EmployeeDocumentRepository(self.db),
            self.user_repo,
            RoleRepository(self.db),
            self.audit_repo,
            self.auth,
        )

    @cached_property
    def tanks(self) -> TankService:
        return TankService(
            TankRepository(self.db),
            TankReadingRepository(self.db),
            TankTransactionRepository(self.db),
            FuelReconciliationRepository(self.db),
            self.fuel_repo,
            self.employee_repo,
            self.audit_repo,
            self.auth,
            assignment_repo=NozzleAssignmentRepository(self.db),
        )
