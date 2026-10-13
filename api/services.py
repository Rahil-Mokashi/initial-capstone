"""Builds the service objects for ONE request.

Wiring mirrors AppController (app/ui/main_window.py): same repositories,
same constructor arguments. The only difference is lifetime: the Qt app
shares one long-lived Session on its UI thread; a threaded HTTP server must
not, so every request gets its own Session and its own services. Every
service is built lazily, so a request only pays for what it uses.
"""

from functools import cached_property

from sqlalchemy.orm import Session

from app.database import connection as db_connection
from app.repositories.app_setting_repository import AppSettingRepository
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.check_repository import CheckExplanationRepository, CheckResultRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.dispenser_repository import DispenserRepository
from app.repositories.employee_cash_shortage_repository import EmployeeCashShortageRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.employee_shortage_recovery_repository import EmployeeShortageRecoveryRepository
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.fuel_delivery_repository import FuelDeliveryRepository
from app.repositories.fuel_price_history_repository import FuelPriceHistoryRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.leave_request_repository import LeaveRequestRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.pump_setting_repository import PumpSettingRepository
from app.repositories.bank_repositories import BankRepository
from app.repositories.payroll_repositories import PayrollRepository
from app.repositories.credit_repositories import (
    BillDetailRepository,
    CreditOverrideRepository,
    CustomerApprovalRepository,
    FollowUpRepository,
)
from app.repositories.site_repositories import (
    BowserRepository,
    InternalFuelUseRepository,
    LubricantItemRepository,
    LubricantMovementRepository,
    ReportQueryRepository,
    ShiftTenderEntryRepository,
)
from app.repositories.purchase_order_repository import PurchaseOrderItemRepository, PurchaseOrderRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_bank_deposit_repository import ShiftBankDepositRepository
from app.repositories.shift_cash_book_repository import ShiftCashBookRepository
from app.repositories.shift_reconciliation_line_repository import ShiftReconciliationLineRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.supplier_invoice_repository import SupplierInvoiceRepository, SupplierPaymentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.tender_repository import TenderRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.analytics_service import AnalyticsService
from app.services.attendance_service import AttendanceService
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService
from app.services.close_desk_service import CloseDeskService
from app.services.entry_workflow_service import EntryWorkflowService
from app.services.workflow_checks import WorkflowChecks
from app.services.shift_close_service import ShiftCloseService
from app.services.payroll_checks import PayrollChecks
from app.services.payroll_service import PayrollService
from app.services.bank_checks import BankChecks
from app.services.bank_recon_service import BankReconService
from app.services.bowser_service import BowserService
from app.services.check_runners import ExistingDataChecks
from app.services.credit_checks import CreditChecks
from app.services.credit_control_service import CreditControlService
from app.services.customer_ledger_service import CustomerLedgerService
from app.services.daily_report_plus import ReportFinaliser, build_extras
from app.services.daily_report_service import DailyReportService
from app.services.check_service import CheckService
from app.services.credit_service import CreditService
from app.services.dashboard_service import DashboardService
from app.services.employee_service import EmployeeService
from app.services.employee_shortage_service import EmployeeShortageService
from app.services.expense_service import ExpenseService
from app.services.fuel_service import FuelService
from app.services.internal_fuel_service import InternalFuelService
from app.services.leave_service import LeaveService
from app.services.lubricant_service import LubricantService
from app.services.notification_service import NotificationService
from app.services.nozzle_service import NozzleService
from app.services.procurement_service import ProcurementService
from app.services.pump_settings_service import PumpSettingsService
from app.services.report_checks import ReportChecks
from app.services.reconciliation_service import ReconciliationService
from app.services.report_service import ReportService
from app.services.sale_service import SaleService
from app.services.settings_service import SettingsService
from app.services.shift_cash_book_service import ShiftCashBookService
from app.services.shift_service import ShiftService
from app.services.tank_service import TankService
from app.services.tender_entry_service import TenderEntryService
from app.services.user_service import UserService


class Services:
    def __init__(self, db: Session, session_timeout_hours: int):
        self.db = db
        self._timeout = session_timeout_hours

    # ---- repositories used by more than one service -----------------------------
    @cached_property
    def audit_repo(self):
        return AuditLogRepository(self.db)

    @cached_property
    def user_repo(self):
        return UserRepository(self.db)

    @cached_property
    def role_repo(self):
        return RoleRepository(self.db)

    @cached_property
    def employee_repo(self):
        return EmployeeRepository(self.db)

    @cached_property
    def fuel_repo(self):
        return FuelRepository(self.db)

    @cached_property
    def tank_repo(self):
        return TankRepository(self.db)

    @cached_property
    def nozzle_repo(self):
        return NozzleRepository(self.db)

    @cached_property
    def assignment_repo(self):
        return NozzleAssignmentRepository(self.db)

    @cached_property
    def sale_repo(self):
        return SaleRepository(self.db)

    @cached_property
    def customer_repo(self):
        return CustomerRepository(self.db)

    @cached_property
    def tender_repo(self):
        return TenderRepository(self.db)

    @cached_property
    def expense_repo(self):
        return ExpenseRepository(self.db)

    @cached_property
    def shift_repo(self):
        return ShiftRepository(self.db)

    @cached_property
    def attendance_repo(self):
        return AttendanceRepository(self.db)

    @cached_property
    def reconciliation_repo(self):
        return FuelReconciliationRepository(self.db)

    @cached_property
    def shift_reconciliation_repo(self):
        return ShiftReconciliationRepository(self.db)

    @cached_property
    def cash_book_repo(self):
        return ShiftCashBookRepository(self.db)

    @cached_property
    def shortage_recovery_repo(self):
        return EmployeeShortageRecoveryRepository(self.db)

    @cached_property
    def credit_account_repo(self):
        return CreditAccountRepository(self.db)

    @cached_property
    def payment_repo(self):
        return PaymentRepository(self.db)

    @cached_property
    def purchase_order_repo(self):
        return PurchaseOrderRepository(self.db)

    # ---- services ----------------------------------------------------------------
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
        return UserService(self.user_repo, self.role_repo, self.audit_repo, self.auth)

    @cached_property
    def employees(self) -> EmployeeService:
        return EmployeeService(
            self.employee_repo,
            EmployeeDocumentRepository(self.db),
            self.user_repo,
            self.role_repo,
            self.audit_repo,
            self.auth,
        )

    @cached_property
    def attendance(self) -> AttendanceService:
        return AttendanceService(self.attendance_repo, self.employee_repo, self.shift_repo, self.audit_repo, self.auth)

    @cached_property
    def leave(self) -> LeaveService:
        return LeaveService(
            LeaveRequestRepository(self.db),
            self.employee_repo,
            self.audit_repo,
            self.auth,
            attendance_service=self.attendance,
        )

    @cached_property
    def shifts(self) -> ShiftService:
        service = ShiftService(
            self.shift_repo,
            self.assignment_repo,
            self.employee_repo,
            self.nozzle_repo,
            self.user_repo,
            self.audit_repo,
            self.auth,
        )
        service.attach_sale_service(self.sales)  # as AppController does
        return service

    @cached_property
    def fuel(self) -> FuelService:
        return FuelService(self.fuel_repo, FuelPriceHistoryRepository(self.db), self.audit_repo, self.auth)

    @cached_property
    def nozzles(self) -> NozzleService:
        return NozzleService(
            DispenserRepository(self.db),
            self.nozzle_repo,
            self.fuel_repo,
            self.assignment_repo,
            self.audit_repo,
            self.auth,
            self.tank_repo,
        )

    @cached_property
    def tanks(self) -> TankService:
        return TankService(
            self.tank_repo,
            TankReadingRepository(self.db),
            TankTransactionRepository(self.db),
            self.reconciliation_repo,
            self.fuel_repo,
            self.employee_repo,
            self.audit_repo,
            self.auth,
            assignment_repo=self.assignment_repo,
        )

    @cached_property
    def backups(self) -> BackupService:
        return BackupService(db_connection.DB_PATH, self.audit_repo, self.auth)

    @cached_property
    def audit(self) -> AuditService:
        return AuditService(self.audit_repo, self.auth)

    @cached_property
    def settings(self) -> SettingsService:
        return SettingsService(AppSettingRepository(self.db), self.audit_repo, self.auth)

    @cached_property
    def procurement(self) -> ProcurementService:
        return ProcurementService(
            SupplierRepository(self.db),
            self.purchase_order_repo,
            PurchaseOrderItemRepository(self.db),
            FuelDeliveryRepository(self.db),
            SupplierInvoiceRepository(self.db),
            SupplierPaymentRepository(self.db),
            self.fuel_repo,
            self.employee_repo,
            self.tanks,
            self.audit_repo,
            self.auth,
        )

    @cached_property
    def expenses(self) -> ExpenseService:
        return ExpenseService(
            self.expense_repo,
            ExpenseCategoryRepository(self.db),
            self.employee_repo,
            self.shift_repo,
            self.audit_repo,
            self.auth,
            tank_service=self.tanks,
            tender_repo=self.tender_repo,
        )

    @cached_property
    def reconciliation(self) -> ReconciliationService:
        return ReconciliationService(
            self.shift_reconciliation_repo,
            self.shift_repo,
            self.sale_repo,
            self.expense_repo,
            self.audit_repo,
            self.auth,
            self.tender_repo,
        )

    @cached_property
    def cash_book(self) -> ShiftCashBookService:
        return ShiftCashBookService(
            self.cash_book_repo,
            self.shift_repo,
            self.audit_repo,
            self.auth,
            ShiftBankDepositRepository(self.db),
            shortage_recovery_repo=self.shortage_recovery_repo,
        )

    @cached_property
    def shortages(self) -> EmployeeShortageService:
        return EmployeeShortageService(
            EmployeeCashShortageRepository(self.db),
            self.shortage_recovery_repo,
            ShiftReconciliationLineRepository(self.db),
            self.employee_repo,
            ExpenseCategoryRepository(self.db),
            self.expenses,
            self.audit_repo,
            self.auth,
            self.cash_book_repo,
        )

    @cached_property
    def credit(self) -> CreditService:
        return CreditService(
            self.credit_account_repo,
            CustomerPaymentRepository(self.db),
            self.customer_repo,
            self.sale_repo,
            self.audit_repo,
            self.auth,
        )

    @cached_property
    def sales(self) -> SaleService:
        return SaleService(
            self.sale_repo,
            self.shift_repo,
            self.nozzle_repo,
            self.fuel_repo,
            self.employee_repo,
            self.customer_repo,
            self.tank_repo,
            self.tanks,
            self.audit_repo,
            self.auth,
            self.payment_repo,
            self.credit,
            tender_repo=self.tender_repo,
        )

    @cached_property
    def dashboard(self) -> DashboardService:
        return DashboardService(self.sale_repo, self.shift_repo, self.tank_repo, self.purchase_order_repo, self.auth)

    @cached_property
    def reports(self) -> ReportService:
        return ReportService(
            self.fuel_repo,
            self.tank_repo,
            self.nozzle_repo,
            self.reconciliation_repo,
            self.auth,
            self.sale_repo,
            self.payment_repo,
            self.expense_repo,
            self.credit_account_repo,
            CustomerPaymentRepository(self.db),
            self.customer_repo,
            self.shift_reconciliation_repo,
            TankTransactionRepository(self.db),
            self.attendance_repo,
            self.employee_repo,
            self.shift_repo,
        )

    @cached_property
    def analytics(self) -> AnalyticsService:
        return AnalyticsService(
            self.sale_repo, self.expense_repo, PurchaseOrderItemRepository(self.db), self.fuel_repo, self.auth
        )

    @cached_property
    def notifications(self) -> NotificationService:
        return NotificationService(
            tank_repo=self.tank_repo,
            fuel_reconciliation_repo=self.reconciliation_repo,
            shift_reconciliation_repo=self.shift_reconciliation_repo,
            expense_repo=self.expense_repo,
            employee_repo=self.employee_repo,
            attendance_repo=self.attendance_repo,
            credit_account_repo=self.credit_account_repo,
            supplier_invoice_repo=SupplierInvoiceRepository(self.db),
            supplier_payment_repo=SupplierPaymentRepository(self.db),
            audit_repo=self.audit_repo,
            credit_service=self.credit,
            auth_service=self.auth,
            db_path=db_connection.DB_PATH,
        )

    # ---- site-visit build (2026-10-12) --------------------------------------------
    @cached_property
    def pump_settings(self) -> PumpSettingsService:
        return PumpSettingsService(PumpSettingRepository(self.db), self.audit_repo, self.auth)

    @cached_property
    def checks(self) -> CheckService:
        return CheckService(CheckResultRepository(self.db), CheckExplanationRepository(self.db), self.audit_repo, self.auth)

    @cached_property
    def existing_checks(self) -> ExistingDataChecks:
        return ExistingDataChecks(
            self.checks, self.pump_settings, self.shift_repo, self.assignment_repo, self.sale_repo,
            ShiftReconciliationRepository(self.db), FuelReconciliationRepository(self.db), self.tank_repo,
            self.credit_account_repo, CustomerPaymentRepository(self.db),
        )

    @cached_property
    def lubricants(self) -> LubricantService:
        return LubricantService(
            LubricantItemRepository(self.db), LubricantMovementRepository(self.db), self.shift_repo, self.audit_repo, self.auth
        )

    @cached_property
    def bowser(self) -> BowserService:
        return BowserService(
            BowserRepository(self.db), self.customer_repo, self.credit_account_repo, self.sales, self.shift_repo,
            self.audit_repo, self.auth,
        )

    @cached_property
    def tender_entries(self) -> TenderEntryService:
        return TenderEntryService(
            ShiftTenderEntryRepository(self.db), self.tender_repo, self.shift_repo, self.audit_repo, self.auth
        )

    @cached_property
    def internal_fuel(self) -> InternalFuelService:
        return InternalFuelService(
            InternalFuelUseRepository(self.db), ExpenseCategoryRepository(self.db), self.fuel_repo, self.expenses,
            self.pump_settings, self.audit_repo, self.auth,
        )

    @cached_property
    def daily_report(self) -> DailyReportService:
        return DailyReportService(
            self.shift_repo, self.tank_repo, self.sale_repo, self.expense_repo, self.assignment_repo,
            ReportQueryRepository(self.db), self.cash_book, self.tender_entries, self.lubricants, self.bowser,
            self.pump_settings, InternalFuelUseRepository(self.db), self.auth, self.audit_repo,
        )

    @cached_property
    def credit_ledger(self) -> CustomerLedgerService:
        return CustomerLedgerService(
            self.customer_repo, self.credit_account_repo, self.sale_repo, CustomerPaymentRepository(self.db),
            BowserRepository(self.db), BillDetailRepository(self.db), self.auth,
        )

    @cached_property
    def credit_control(self) -> CreditControlService:
        return CreditControlService(
            self.credit_ledger, self.credit_account_repo, CustomerApprovalRepository(self.db), CreditOverrideRepository(self.db),
            FollowUpRepository(self.db), BillDetailRepository(self.db), self.sale_repo, self.pump_settings, self.user_repo,
            self.auth, self.audit_repo, self.credit,
        )

    @cached_property
    def bank(self) -> BankReconService:
        return BankReconService(BankRepository(self.db), self.pump_settings, self.audit_repo, self.auth)

    @cached_property
    def bank_checks(self) -> BankChecks:
        return BankChecks(self.bank, BankRepository(self.db), self.checks, self.pump_settings)

    @cached_property
    def shift_close(self) -> ShiftCloseService:
        return ShiftCloseService(
            self.shifts, self.shift_repo, self.assignment_repo, self.nozzle_repo, self.employee_repo, self.audit_repo, self.auth
        )

    @cached_property
    def entries(self) -> EntryWorkflowService:
        return EntryWorkflowService(self.db, self.audit_repo, self.auth, self.pump_settings)

    @cached_property
    def workflow_checks(self) -> WorkflowChecks:
        return WorkflowChecks(self.checks, self.entries)

    @cached_property
    def close_desk(self) -> CloseDeskService:
        return CloseDeskService(self.shift_close, self.tender_entries, self.cash_book, self.daily_report, self.shift_repo, self.pump_settings, self.auth, self.entries)

    @cached_property
    def payroll(self) -> PayrollService:
        return PayrollService(PayrollRepository(self.db), self.pump_settings, self.audit_repo, self.auth)

    @cached_property
    def payroll_checks(self) -> PayrollChecks:
        return PayrollChecks(self.payroll, PayrollRepository(self.db), self.checks, BankRepository(self.db))

    @cached_property
    def credit_checks(self) -> CreditChecks:
        return CreditChecks(
            self.credit_ledger, self.credit_control, self.checks, self.sale_repo, self.shift_repo, self.credit_account_repo
        )

    def estimate_sale_amount(self, nozzle_id, quantity):
        """What a sale of `quantity` litres at this nozzle will come to (the fuel's current price), for the credit check."""
        from decimal import Decimal

        from app.core.money import money, volume

        nozzle = self.nozzle_repo.get_by_id(nozzle_id)
        rate = Decimal(str(nozzle.fuel.rate_per_liter)) if nozzle and nozzle.fuel and nozzle.fuel.rate_per_liter else Decimal("0")
        return money(volume(quantity) * rate)

    def create_credit_aware_sale(self, user_id, data, override=None):
        """Create a sale; if it is on credit, apply the approval rule and the limit first (V-14).
        With an owner's override the existing limit check is stepped over for this one sale and the override is recorded."""
        from app.core.constants import PaymentMethod
        from app.repositories.base import unit_of_work
        from app.services.credit_control_service import Override

        if data.payment_method != PaymentMethod.CREDIT or not data.customer_id:
            return self.sales.create_sale(user_id, data)
        amount = self.estimate_sale_amount(data.nozzle_id, data.quantity)
        ov = (
            Override(override.approver_id, override.credential, override.use_pin, override.reason)
            if override is not None else None
        )
        approved = self.credit_control.authorize_sale(user_id, data.customer_id, amount, ov)
        if approved is None:
            return self.sales.create_sale(user_id, data)
        before = self.credit_control.check_sale(data.customer_id, amount)
        with unit_of_work(self.db):
            with self.credit.limit_override(data.customer_id):
                sale = self.sales.create_sale(user_id, data)
            self.credit_control.record_override(user_id, sale, before, approved)
        return sale

    @cached_property
    def report_checks(self) -> ReportChecks:
        return ReportChecks(self.checks, self.daily_report, self.pump_settings)

    @cached_property
    def report_finaliser(self) -> ReportFinaliser:
        return ReportFinaliser(self.db, self.daily_report, self.audit_repo, self.auth)

    def render_report(self, report, company, style, actor_id):
        """Classic is the exact replica. Plus adds the checks strip and extras around the same layout."""
        from app.services.daily_report_html import render_daily_report

        extras = build_extras(self, report, actor_id) if style == "plus" else None
        return render_daily_report(report, company, extras)

    def run_all_checks(self, actor_id, day):
        """Every check runner for one business date. Later tracks append their runners here."""
        results = list(self.existing_checks.run_day(actor_id, day))
        results += self.report_checks.run_day(actor_id, day)
        results += self.credit_checks.run_day(actor_id, day)
        results += self.bank_checks.run_day(actor_id, day)
        results += self.payroll_checks.run_day(actor_id, day)
        results += self.workflow_checks.run_day(actor_id, day)
        return results

    def days_to_check(self):
        """Today, every day that still has an open shift, and days whose shifts changed in the last minutes."""
        from datetime import date, datetime, timedelta, timezone

        from app.core.constants import ShiftStatus
        from app.models.shift import Shift

        days = {date.today()}
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
        for shift in self.db.query(Shift).filter((Shift.status == ShiftStatus.OPEN.value) | (Shift.updated_at >= cutoff)).all():
            days.add(shift.shift_date)
        return sorted(days)
