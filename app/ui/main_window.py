from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import Permission
from app.core.exceptions import SessionExpiredError
from app.database import connection as db_connection
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.dispenser_repository import DispenserRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.fuel_delivery_repository import FuelDeliveryRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.purchase_order_repository import PurchaseOrderItemRepository, PurchaseOrderRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.supplier_invoice_repository import SupplierInvoiceRepository, SupplierPaymentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.attendance_service import AttendanceService
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.nozzle_service import NozzleService
from app.services.procurement_service import ProcurementService
from app.services.report_service import ReportService
from app.services.shift_service import ShiftService
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.tank_service import TankService
from app.services.user_service import UserService
from app.ui.qt_utils import describe_unexpected_error
from app.ui.styles import STYLESHEET

SESSION_CHECK_INTERVAL_MS = 60_000


class DashboardCard(QWidget):
    """A clickable quick-access tile on the landing dashboard."""

    def __init__(self, icon: str, title: str, subtitle: str, on_click, parent=None):
        super().__init__(parent)
        self.setObjectName("dashCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._on_click = on_click

        icon_label = QLabel(icon)
        icon_label.setObjectName("dashCardIcon")
        icon_label.setFixedSize(46, 46)

        title_label = QLabel(title)
        title_label.setObjectName("dashCardTitle")

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("dashCardSubtitle")
        subtitle_label.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(title_label)
        text_layout.addWidget(subtitle_label)

        layout = QHBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(icon_label)
        layout.addLayout(text_layout, stretch=1)
        self.setLayout(layout)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(108)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(27, 30, 43, 22))
        self.setGraphicsEffect(shadow)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


def _greeting_for_now() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


class MainWindow(QMainWindow):
    """Landing screen after login. Shows the current user and lets them log out."""

    logout_requested = Signal(bool)  # bool: True if the logout was due to session expiry

    def __init__(
        self,
        auth_service: AuthService,
        employee_service: EmployeeService,
        attendance_service: AttendanceService,
        shift_service: ShiftService,
        nozzle_service: NozzleService,
        tank_service: TankService,
        report_service: ReportService,
        user_service: UserService,
        backup_service: BackupService,
        audit_service: AuditService,
        procurement_service: ProcurementService,
        role_repo,
        fuel_repo,
        user_repo,
        user_data: dict,
    ):
        super().__init__()
        self._auth_service = auth_service
        self._employee_service = employee_service
        self._attendance_service = attendance_service
        self._shift_service = shift_service
        self._nozzle_service = nozzle_service
        self._tank_service = tank_service
        self._report_service = report_service
        self._user_service = user_service
        self._backup_service = backup_service
        self._audit_service = audit_service
        self._procurement_service = procurement_service
        self._role_repo = role_repo
        self._fuel_repo = fuel_repo
        self._user_repo = user_repo
        self._user_data = user_data
        self._session_token = user_data["session_token"]
        self._employee_window = None
        self._attendance_window = None
        self._shift_window = None
        self._nozzle_window = None
        self._tank_window = None
        self._my_shift_window = None
        self._report_window = None
        self._user_window = None
        self._backup_window = None
        self._audit_window = None
        self._procurement_window = None

        self.setWindowTitle("Petrol Pump ERP")
        self.setMinimumSize(960, 620)

        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(20, 14, 20, 14)

        user_label = QLabel(user_data["username"])
        user_label.setObjectName("userLabel")

        role_tag = QLabel(user_data.get("role") or "No role")
        role_tag.setObjectName("roleTag")

        account_button = QPushButton("Account")
        account_button.setObjectName("secondaryButton")
        account_button.setCursor(Qt.PointingHandCursor)
        account_menu = QMenu(account_button)
        account_menu.addAction("Change Password", self._open_change_password)
        account_menu.addSeparator()
        account_menu.addAction("Logout", self._logout)
        account_button.setMenu(account_menu)

        top_bar_layout.addWidget(user_label)
        top_bar_layout.addSpacing(8)
        top_bar_layout.addWidget(role_tag)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(account_button)
        top_bar.setLayout(top_bar_layout)

        display_name = user_data.get("first_name") or user_data["username"]
        greeting = QLabel(f"{_greeting_for_now()}, {display_name}")
        greeting.setObjectName("dashGreeting")

        today_label = QLabel(datetime.now().strftime("%A, %d %B %Y"))
        today_label.setObjectName("dashDate")

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        header_layout.addWidget(greeting)
        header_layout.addWidget(today_label)

        card_groups = [
            (
                "DAILY OPERATIONS",
                [
                    ("👥", "Employees", "Staff, documents, and status", self._open_employees, Permission.EMPLOYEE_VIEW),
                    ("🕒", "Attendance", "Mark and review attendance", self._open_attendance, Permission.ATTENDANCE_VIEW),
                    ("⛽", "Shifts", "Open/close shifts, assign nozzles", self._open_shifts, Permission.SHIFT_VIEW),
                    ("🪪", "My Shift", "Your current nozzle and fuel assignment", self._open_my_shift, Permission.MY_ASSIGNMENT_VIEW),
                    ("🔧", "Nozzles", "Manage dispensers and nozzles", self._open_nozzles, Permission.NOZZLE_VIEW),
                    ("🛢️", "Tanks", "Stock, transactions, reconciliation", self._open_tanks, Permission.INVENTORY_VIEW),
                    ("🚛", "Procurement", "Suppliers, orders, and deliveries", self._open_procurement, Permission.PROCUREMENT_VIEW),
                ],
            ),
            (
                "REPORTS & ADMINISTRATION",
                [
                    ("📊", "Reports", "Fuel stock and reconciliation by fuel type", self._open_reports, Permission.INVENTORY_VIEW),
                    ("🔐", "Users", "Create logins and manage roles", self._open_users, Permission.USER_MANAGE),
                    ("🗄️", "Backups", "Back up or restore the database", self._open_backups, Permission.BACKUP_MANAGE),
                    ("📜", "Audit Log", "Review every recorded change", self._open_audit_log, Permission.AUDIT_VIEW),
                ],
            ),
        ]

        CARDS_PER_ROW = 4
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(32, 32, 32, 32)
        body_layout.setSpacing(28)
        body_layout.addLayout(header_layout)

        total_visible_cards = 0
        for group_label, cards in card_groups:
            visible_cards = [
                (icon, title, subtitle, handler)
                for icon, title, subtitle, handler, permission in cards
                if self._auth_service.check_permission(user_data["id"], permission.value)
            ]
            if not visible_cards:
                continue
            total_visible_cards += len(visible_cards)

            group_label_widget = QLabel(group_label)
            group_label_widget.setObjectName("dashGroupLabel")

            group_grid = QGridLayout()
            group_grid.setSpacing(16)
            for column in range(CARDS_PER_ROW):
                group_grid.setColumnStretch(column, 1)
            for index, (icon, title, subtitle, handler) in enumerate(visible_cards):
                row, column = divmod(index, CARDS_PER_ROW)
                group_grid.addWidget(DashboardCard(icon, title, subtitle, handler), row, column)

            group_layout = QVBoxLayout()
            group_layout.setSpacing(10)
            group_layout.addWidget(group_label_widget)
            group_layout.addLayout(group_grid)
            body_layout.addLayout(group_layout)

        if total_visible_cards == 0:
            empty_state = QLabel("Nothing to show yet — ask an administrator for access to a module.")
            empty_state.setObjectName("subtitle")
            body_layout.addWidget(empty_state)
        body_layout.addStretch()

        body = QWidget()
        body.setObjectName("background")
        body.setLayout(body_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(top_bar)
        layout.addWidget(body, stretch=1)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._check_session)
        self._session_timer.start(SESSION_CHECK_INTERVAL_MS)

    def _check_session(self) -> None:
        try:
            self._auth_service.validate_session(self._session_token)
        except SessionExpiredError:
            self._session_timer.stop()
            QMessageBox.information(self, "Session expired", "Your session has expired. Please log in again.")
            self.logout_requested.emit(True)
        except Exception as exc:  # noqa: BLE001 - a periodic timer callback must never crash the app
            describe_unexpected_error(exc)

    def _logout(self) -> None:
        self._session_timer.stop()
        try:
            self._auth_service.logout(self._session_token)
        except Exception as exc:  # noqa: BLE001 - still return the user to the login screen even if this fails
            describe_unexpected_error(exc)
        self.logout_requested.emit(False)

    def _open_employees(self) -> None:
        from app.ui.employee_window import EmployeeListWindow

        self._employee_window = EmployeeListWindow(self._employee_service, self._auth_service, self._user_data["id"])
        self._employee_window.show()

    def _open_attendance(self) -> None:
        from app.ui.attendance_window import AttendanceWindow

        self._attendance_window = AttendanceWindow(
            self._attendance_service, self._employee_service, self._auth_service, self._user_data["id"]
        )
        self._attendance_window.show()

    def _open_shifts(self) -> None:
        from app.ui.shift_window import ShiftListWindow

        self._shift_window = ShiftListWindow(
            self._shift_service, self._employee_service, self._auth_service, self._user_data["id"]
        )
        self._shift_window.show()

    def _open_nozzles(self) -> None:
        from app.ui.nozzle_window import NozzleManagementWindow

        self._nozzle_window = NozzleManagementWindow(
            self._nozzle_service, self._fuel_repo, self._auth_service, self._user_data["id"]
        )
        self._nozzle_window.show()

    def _open_tanks(self) -> None:
        from app.ui.tank_window import TankListWindow

        self._tank_window = TankListWindow(
            self._tank_service, self._employee_service, self._fuel_repo, self._auth_service, self._user_data["id"]
        )
        self._tank_window.show()

    def _open_procurement(self) -> None:
        from app.ui.procurement_window import ProcurementWindow

        self._procurement_window = ProcurementWindow(
            self._procurement_service,
            self._fuel_repo,
            self._tank_service,
            self._employee_service,
            self._auth_service,
            self._user_data["id"],
        )
        self._procurement_window.show()

    def _open_my_shift(self) -> None:
        from app.ui.my_shift_window import MyShiftWindow

        self._my_shift_window = MyShiftWindow(self._shift_service, self._auth_service, self._user_data["id"])
        self._my_shift_window.show()

    def _open_reports(self) -> None:
        from app.ui.report_window import FuelTypeSummaryReportWindow

        self._report_window = FuelTypeSummaryReportWindow(
            self._report_service, self._auth_service, self._user_data["id"]
        )
        self._report_window.show()

    def _open_users(self) -> None:
        from app.ui.user_management_window import UserListWindow

        self._user_window = UserListWindow(self._user_service, self._role_repo, self._user_data["id"])
        self._user_window.show()

    def _open_backups(self) -> None:
        from app.ui.backup_window import BackupWindow

        self._backup_window = BackupWindow(self._backup_service, self._user_data["id"])
        self._backup_window.show()

    def _open_audit_log(self) -> None:
        from app.ui.audit_log_window import AuditLogWindow

        self._audit_window = AuditLogWindow(self._audit_service, self._user_repo, self._user_data["id"])
        self._audit_window.show()

    def _open_change_password(self) -> None:
        from app.ui.change_password_dialog import ChangePasswordDialog

        dialog = ChangePasswordDialog(self._user_service, self._user_data["id"], forced=False, parent=self)
        dialog.exec()


class AppController:
    """Owns the login <-> main window transition and the shared AuthService."""

    def __init__(self):
        self._db_session = db_connection.SessionLocal()
        user_repo = UserRepository(self._db_session)
        audit_repo = AuditLogRepository(self._db_session)
        self._role_repo = RoleRepository(self._db_session)
        self._auth_service = AuthService(
            user_repo,
            audit_repo,
            UserSessionRepository(self._db_session),
        )
        self._user_service = UserService(
            user_repo,
            self._role_repo,
            audit_repo,
            self._auth_service,
        )
        employee_repo = EmployeeRepository(self._db_session)
        self._employee_service = EmployeeService(
            employee_repo,
            EmployeeDocumentRepository(self._db_session),
            user_repo,
            self._role_repo,
            audit_repo,
            self._auth_service,
        )
        self._attendance_service = AttendanceService(
            AttendanceRepository(self._db_session),
            employee_repo,
            audit_repo,
            self._auth_service,
        )
        nozzle_repo = NozzleRepository(self._db_session)
        nozzle_assignment_repo = NozzleAssignmentRepository(self._db_session)
        self._shift_service = ShiftService(
            ShiftRepository(self._db_session),
            nozzle_assignment_repo,
            employee_repo,
            nozzle_repo,
            user_repo,
            audit_repo,
            self._auth_service,
        )
        self._fuel_repo = FuelRepository(self._db_session)
        self._nozzle_service = NozzleService(
            DispenserRepository(self._db_session),
            nozzle_repo,
            self._fuel_repo,
            nozzle_assignment_repo,
            audit_repo,
            self._auth_service,
        )
        tank_repo = TankRepository(self._db_session)
        reconciliation_repo = FuelReconciliationRepository(self._db_session)
        self._tank_service = TankService(
            tank_repo,
            TankReadingRepository(self._db_session),
            TankTransactionRepository(self._db_session),
            reconciliation_repo,
            self._fuel_repo,
            employee_repo,
            audit_repo,
            self._auth_service,
        )
        self._report_service = ReportService(
            self._fuel_repo,
            tank_repo,
            nozzle_repo,
            reconciliation_repo,
            self._auth_service,
        )
        self._backup_service = BackupService(
            db_connection.DB_PATH,
            audit_repo,
            self._auth_service,
        )
        self._audit_service = AuditService(audit_repo, self._auth_service)
        self._procurement_service = ProcurementService(
            SupplierRepository(self._db_session),
            PurchaseOrderRepository(self._db_session),
            PurchaseOrderItemRepository(self._db_session),
            FuelDeliveryRepository(self._db_session),
            SupplierInvoiceRepository(self._db_session),
            SupplierPaymentRepository(self._db_session),
            self._fuel_repo,
            employee_repo,
            self._tank_service,
            audit_repo,
            self._auth_service,
        )
        self._user_repo = user_repo
        self.login_window = None
        self.main_window = None

    def start(self) -> None:
        self._show_login()

    def _show_login(self) -> None:
        from app.ui.login_window import LoginWindow

        self.main_window = None
        self.login_window = LoginWindow(self._auth_service)
        self.login_window.login_succeeded.connect(self._show_main_window)
        self.login_window.show()

    def _show_main_window(self, user_data: dict) -> None:
        if self.login_window:
            self.login_window.close()
            self.login_window = None

        if user_data.get("must_change_password"):
            from app.ui.change_password_dialog import ChangePasswordDialog

            dialog = ChangePasswordDialog(self._user_service, user_data["id"], forced=True)
            dialog.exec()
            user_data = dict(user_data, must_change_password=False)

        self.main_window = MainWindow(
            self._auth_service,
            self._employee_service,
            self._attendance_service,
            self._shift_service,
            self._nozzle_service,
            self._tank_service,
            self._report_service,
            self._user_service,
            self._backup_service,
            self._audit_service,
            self._procurement_service,
            self._role_repo,
            self._fuel_repo,
            self._user_repo,
            user_data,
        )
        self.main_window.logout_requested.connect(self._on_logout)
        self.main_window.show()

    def _on_logout(self, _expired: bool) -> None:
        if self.main_window:
            self.main_window.close()
            self.main_window = None
        self._show_login()


def launch_app() -> None:
    app = QApplication([])
    app.setStyleSheet(STYLESHEET)
    controller = AppController()
    controller.start()
    app.exec()
