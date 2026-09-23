import contextlib
import platform
from datetime import date, datetime

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from app.core.config import settings
from app.core.constants import AssignmentStatus, NotificationCategory, Permission, ShiftStatus
from app.core.exceptions import SessionExpiredError
from app.database import connection as db_connection
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.app_setting_repository import AppSettingRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.dispenser_repository import DispenserRepository
from app.repositories.employee_cash_shortage_repository import EmployeeCashShortageRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_shortage_recovery_repository import EmployeeShortageRecoveryRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.fuel_delivery_repository import FuelDeliveryRepository
from app.repositories.fuel_price_history_repository import FuelPriceHistoryRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.leave_request_repository import LeaveRequestRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.purchase_order_repository import PurchaseOrderItemRepository, PurchaseOrderRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.shift_bank_deposit_repository import ShiftBankDepositRepository
from app.repositories.shift_cash_book_repository import ShiftCashBookRepository
from app.repositories.shift_reconciliation_line_repository import ShiftReconciliationLineRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
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
from app.services.auth_service import AuthService
from app.services.credit_service import CreditService
from app.services.dashboard_service import DashboardService
from app.services.employee_service import EmployeeService
from app.services.expense_service import ExpenseService
from app.services.fuel_service import FuelService
from app.services.leave_service import LeaveService
from app.services.settings_service import SettingsService
from app.services.notification_service import NotificationService
from app.services.nozzle_service import NozzleService
from app.services.procurement_service import ProcurementService
from app.services.reconciliation_service import ReconciliationService
from app.services.employee_shortage_service import EmployeeShortageService
from app.services.shift_cash_book_service import ShiftCashBookService
from app.services.report_service import ReportService
from app.services.sale_service import SaleService
from app.services.shift_service import ShiftService
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.tank_service import TankService
from app.services.user_service import UserService
from app.ui.background import is_widget_alive
from app.ui.qt_utils import apply_hard_shadow, describe_unexpected_error
from app.ui.sidebar import HEADER_HEIGHT, SIDEBAR_WIDTH, Sidebar
from app.ui.theme import apply_theme, is_dark_mode, set_dark_mode
from app.ui.widgets import GridBackgroundWidget, TankGaugeCard

SESSION_CHECK_INTERVAL_MS = 60_000

# Shared page margin used by both the top bar and the dashboard body so
# their content lines up on the same left/right edge - previously the
# top bar used 20px and the body used 32px, which made the two feel
# misaligned and unbalanced against each other.
DASHBOARD_PAGE_MARGIN = 24

# Used to compute how many dashboard-card columns fit the current
# window width (see MainWindow._compute_card_columns), so the grid
# actually reflows on resize instead of staying pinned at 4 columns
# regardless of how narrow or wide the window is.
DASHBOARD_CARD_TARGET_WIDTH = 240
DASHBOARD_MAX_CARD_COLUMNS = 4

# Tank gauges are visually heavier than a stat tile (each carries its own
# fill gauge), so they cap out at fewer columns than the stat strip does
# even on a wide window - matches tank_window.py's own GAUGE_COLUMNS.
DASHBOARD_TANK_GAUGE_MAX_COLUMNS = 3

# How many items the dashboard's own condensed alert list / shift roster
# show before deferring to their "view all" / "+N more" overflow - the
# full, uncapped list already exists one click away (the Alerts screen,
# the Shifts screen), so the dashboard only needs enough to be useful at
# a glance, not to be a second copy of either screen.
ALERTS_SHOWN_ON_DASHBOARD = 3
ROSTER_ROWS_SHOWN_ON_DASHBOARD = 6


class StatCard(QWidget):
    """A small at-a-glance KPI tile at the top of the dashboard (today's
    sales, open shifts, tanks needing attention, pending purchase orders)."""

    def __init__(self, value: str, label: str, tone: str = "normal", parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setProperty("tone", tone)
        self.setAttribute(Qt.WA_StyledBackground, True)

        value_label = QLabel(value)
        value_label.setObjectName("statValue")

        caption_label = QLabel(label)
        caption_label.setObjectName("statLabel")
        caption_label.setProperty("tone", tone)

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(80)

        apply_hard_shadow(self)


def compute_dashboard_columns(window_width: int) -> int:
    """How many dashboard-card columns fit a window this wide - a pure
    function (no Qt state) so it's testable without constructing a full
    MainWindow, which needs its entire service graph wired up."""

    available_width = window_width - 2 * DASHBOARD_PAGE_MARGIN
    columns = available_width // DASHBOARD_CARD_TARGET_WIDTH
    return max(1, min(DASHBOARD_MAX_CARD_COLUMNS, columns))


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
        leave_service: LeaveService,
        shift_service: ShiftService,
        nozzle_service: NozzleService,
        tank_service: TankService,
        report_service: ReportService,
        user_service: UserService,
        backup_service: BackupService,
        audit_service: AuditService,
        procurement_service: ProcurementService,
        sale_service: SaleService,
        credit_service: CreditService,
        expense_service: ExpenseService,
        reconciliation_service: ReconciliationService,
        cash_book_service: ShiftCashBookService,
        employee_shortage_service: EmployeeShortageService,
        analytics_service: AnalyticsService,
        dashboard_service: DashboardService,
        fuel_service: FuelService,
        settings_service: SettingsService,
        notification_service,
        role_repo,
        fuel_repo,
        user_repo,
        tank_repo,
        user_data: dict,
    ):
        super().__init__()
        self._auth_service = auth_service
        self._employee_service = employee_service
        self._attendance_service = attendance_service
        self._leave_service = leave_service
        self._shift_service = shift_service
        self._nozzle_service = nozzle_service
        self._tank_service = tank_service
        self._report_service = report_service
        self._user_service = user_service
        self._backup_service = backup_service
        self._audit_service = audit_service
        self._procurement_service = procurement_service
        self._sale_service = sale_service
        self._credit_service = credit_service
        self._expense_service = expense_service
        self._reconciliation_service = reconciliation_service
        self._cash_book_service = cash_book_service
        self._employee_shortage_service = employee_shortage_service
        self._analytics_service = analytics_service
        self._dashboard_service = dashboard_service
        self._fuel_service = fuel_service
        self._settings_service = settings_service
        self._notification_service = notification_service
        self._role_repo = role_repo
        self._fuel_repo = fuel_repo
        self._user_repo = user_repo
        self._tank_repo = tank_repo
        self._user_data = user_data
        self._session_token = user_data["session_token"]
        # Every module used to be its own top-level popup window, each
        # tracked by one of these attributes so it wouldn't be garbage
        # collected out from under itself. Now every module is an
        # embedded page inside self._content_stack instead (see
        # _open_module_page/_push_subpage below) - _page_stack holds the
        # equivalent references for whatever is currently on screen.
        self._page_stack: list[tuple[QWidget, str, str | None]] = []

        self.setWindowTitle("Petrol Pump ERP")
        # 960 was sized for the old top-bar-only chrome; the sidebar now
        # permanently occupies SIDEBAR_WIDTH of that, so the minimum was
        # widened to keep the same amount of breathing room for content.
        self.setMinimumSize(960 + SIDEBAR_WIDTH, 620)

        display_name = user_data.get("first_name") or user_data["username"]
        full_name = " ".join(part for part in (user_data.get("first_name"), user_data.get("last_name")) if part) or user_data["username"]

        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(HEADER_HEIGHT)
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(DASHBOARD_PAGE_MARGIN, 14, DASHBOARD_PAGE_MARGIN, 14)
        top_bar_layout.setSpacing(12)

        # A single searchable index across the modules this user can
        # actually see (built from the same is_card_visible gate the
        # sidebar/dashboard use), so typing here can never surface a
        # record the sidebar itself would have hidden. Rebuilt on every
        # focus rather than once at login, so a record added mid-shift
        # (a new employee, a new nozzle) is findable without a restart.
        self._search_index: dict[str, callable] = {}
        self.search_input = QLineEdit()
        self.search_input.setObjectName("topBarSearch")
        self.search_input.setPlaceholderText("Search employees, nozzles, tanks…")
        self.search_input.setToolTip("Search (Ctrl+F)")
        self.search_input.setFixedWidth(280)
        self.search_input.setClearButtonEnabled(True)
        self._search_completer = QCompleter([])
        self._search_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._search_completer.setFilterMode(Qt.MatchContains)
        self._search_completer.setCompletionMode(QCompleter.PopupCompletion)
        self._search_completer.activated[str].connect(self._handle_search_selected)
        self.search_input.setCompleter(self._search_completer)
        self.search_input.installEventFilter(self)
        self._rebuild_search_index()

        # Ticks every second so the bar reads as genuinely live rather
        # than a date stamped once at login - cheap, since it only ever
        # updates one label's text.
        self.clock_label = QLabel("")
        self.clock_label.setObjectName("topBarClock")
        self._update_clock()
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        # problemstatement.md #37 explicitly asks for an "offline status
        # indicator" and #1 makes offline the whole premise of this
        # product (no web framework, no cloud database, no online sync,
        # ever). This app never has a network dependency to lose in the
        # first place, so there is nothing to poll or ping - a static
        # badge stating the fact is the honest indicator, not a live
        # connectivity check for a connection this app never opens.
        self.offline_indicator_label = QLabel("● Offline — Local Only")
        self.offline_indicator_label.setObjectName("topBarOfflineBadge")
        self.offline_indicator_label.setToolTip(
            "This app runs entirely on this computer. It never needs, and never uses, an internet connection."
        )

        # problemstatement.md #37's "current shift indicator" - whether a
        # shift is open on this pump right now, without having to open
        # the Shift screen to find out. Starts with a neutral placeholder
        # (matching the AlertStrip's own "Checking…" pattern) rather than
        # querying the database here in __init__ - see the long-standing
        # comment on refresh_alert_badge for why an early DB read from a
        # still-settling widget tree previously caused a real crash.
        # Populated by refresh_shift_indicator, on the same session-timer
        # tick that already refreshes the Alerts badge.
        self.shift_indicator_label = QLabel("Shift: —")
        self.shift_indicator_label.setObjectName("topBarShiftIndicator")

        # The alert count belongs in the top bar rather than on a dashboard
        # card, because it must be visible from every state of this screen
        # - including when the operator has scrolled the cards out of view.
        # It carries the count itself so an unattended critical problem is
        # apparent without opening anything.
        self.alerts_button = QPushButton("Alerts")
        self.alerts_button.setObjectName("alertsButton")
        self.alerts_button.setCursor(Qt.PointingHandCursor)
        self._alerts_menu = QMenu(self.alerts_button)
        self._alerts_menu.setObjectName("alertsMenu")
        self._alerts_menu.aboutToShow.connect(self._populate_alerts_menu)
        self.alerts_button.setMenu(self._alerts_menu)

        # The account control doubles as the identity display (an
        # initials avatar + name, replacing the old separate "admin" /
        # "ADMIN" pair) and the entry point to account actions - one
        # element instead of three, each carrying more than it used to.
        account_button = QPushButton(f"  {display_name}")
        account_button.setObjectName("accountButton")
        account_button.setCursor(Qt.PointingHandCursor)
        account_button.setIconSize(QSize(26, 26))
        self._account_button = account_button
        account_menu = QMenu(account_button)
        account_menu.setObjectName("accountMenu")
        self._account_header_widget, self._account_header_labels = self._build_account_header(user_data, full_name)
        header_action = QWidgetAction(account_menu)
        header_action.setDefaultWidget(self._account_header_widget)
        account_menu.addAction(header_action)
        account_menu.addSeparator()
        account_menu.addAction("Change Password", self._open_change_password)
        account_menu.addSeparator()
        self._dark_mode_action = account_menu.addAction("Dark Mode")
        self._dark_mode_action.setCheckable(True)
        self._dark_mode_action.setChecked(is_dark_mode())
        self._dark_mode_action.toggled.connect(self._toggle_dark_mode)
        account_menu.addSeparator()
        account_menu.addAction("Logout", self._logout)
        account_button.setMenu(account_menu)
        self._refresh_account_avatar()

        top_bar_layout.addWidget(self.search_input)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.offline_indicator_label)
        top_bar_layout.addSpacing(12)
        top_bar_layout.addWidget(self.shift_indicator_label)
        top_bar_layout.addSpacing(16)
        top_bar_layout.addWidget(self.clock_label)
        top_bar_layout.addSpacing(16)
        top_bar_layout.addWidget(self.alerts_button)
        top_bar_layout.addSpacing(8)
        top_bar_layout.addWidget(account_button)
        top_bar.setLayout(top_bar_layout)

        greeting = QLabel(f"{_greeting_for_now()}, {display_name}")
        greeting.setObjectName("dashGreeting")

        today_label = QLabel(datetime.now().strftime("%A, %d %B %Y"))
        today_label.setObjectName("dashDate")

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        header_layout.addWidget(greeting)
        header_layout.addWidget(today_label)

        # Imported here, once, rather than inside each factory lambda below
        # (a lambda body cannot contain an import statement) - this keeps
        # every module's UI class import deferred until a real login
        # reaches this point (same lazy-import spirit the old per-module
        # _open_* methods had), just resolved together instead of one at a
        # time on first visit.
        from app.ui.attendance_window import AttendanceWindow
        from app.ui.audit_log_window import AuditLogWindow
        from app.ui.backup_window import BackupWindow
        from app.ui.credit_window import CreditWindow
        from app.ui.employee_window import EmployeeListWindow
        from app.ui.expense_window import ExpenseWindow
        from app.ui.fuel_price_window import FuelPriceWindow
        from app.ui.leave_window import LeaveWindow
        from app.ui.my_shift_window import MyShiftWindow
        from app.ui.nozzle_window import NozzleManagementWindow
        from app.ui.procurement_window import ProcurementWindow
        from app.ui.reconciliation_window import ReconciliationWindow
        from app.ui.sales_window import SalesWindow
        from app.ui.settings_window import SettingsWindow
        from app.ui.shift_window import ShiftListWindow
        from app.ui.tank_window import TankListWindow
        from app.ui.terminal_window import TerminalWindow
        from app.ui.user_management_window import UserListWindow

        # Driven entirely from this one structure (2026-09-16 navigation
        # restructure, matching the client-supplied Morex reference): the
        # sidebar shows one row per top-level group, and each group's
        # landing page (app/ui/group_landing_window.py) renders these same
        # subgroups/items as tiles - neither is a second, separately
        # maintained list. Shape: (GROUP_LABEL, [(subheading, [(title,
        # subtitle, factory, permission), ...])]).
        #
        # Reports is deliberately NOT part of this structure: it is
        # already its own landing page (ReportsHubWindow), so it is wired
        # directly as a fourth sidebar entry below rather than wrapped in
        # a redundant outer landing page of its own.
        #
        # Customers, Expense Categories, and a standalone Dispensers
        # screen have no dedicated window yet (see PROJECT_CONTEXT.md,
        # 2026-09-16) and are deliberately left out rather than given a
        # tile with nowhere real to go: customer records live inside
        # Credit, expense categories are fixed/seeded data with no CRUD
        # screen, and dispensers are already managed together with
        # nozzles below. Bowser is out of scope until it exists.
        self._card_groups = [
            (
                "MASTERS",
                [
                    (
                        "People",
                        [
                            (
                                "Employees", "Add staff, track documents, and set active/inactive status.",
                                lambda: EmployeeListWindow(self._employee_service, self._auth_service, self._user_data["id"]),
                                Permission.EMPLOYEE_VIEW,
                            ),
                            (
                                "Users", "Create logins, assign roles, and unlock or deactivate accounts.",
                                lambda: UserListWindow(self._user_service, self._role_repo, self._user_data["id"]),
                                Permission.USER_MANAGE,
                            ),
                        ],
                    ),
                    (
                        "Fuel & Inventory",
                        [
                            (
                                "Fuel Prices", "Set today's selling rate per fuel and view its price history.",
                                lambda: FuelPriceWindow(self._user_data["id"], self._fuel_service, self._auth_service),
                                Permission.FUEL_PRICE_VIEW,
                            ),
                            (
                                "Tanks", "Register tanks, record dip readings, and reconcile physical stock.",
                                lambda: TankListWindow(
                                    self._tank_service, self._employee_service, self._fuel_repo, self._auth_service, self._user_data["id"]
                                ),
                                Permission.INVENTORY_VIEW,
                            ),
                            (
                                "Nozzles & Dispensers", "Register dispensers and their nozzles, and assign a fuel to each.",
                                lambda: NozzleManagementWindow(
                                    self._nozzle_service, self._fuel_repo, self._tank_repo, self._auth_service, self._user_data["id"]
                                ),
                                Permission.NOZZLE_VIEW,
                            ),
                        ],
                    ),
                    (
                        "Procurement",
                        [
                            (
                                "Suppliers", "Add suppliers and view what has been ordered from each.",
                                lambda: ProcurementWindow(
                                    self._procurement_service, self._fuel_repo, self._tank_service,
                                    self._employee_service, self._auth_service, self._user_data["id"], initial_tab=0,
                                ),
                                Permission.PROCUREMENT_VIEW,
                            ),
                        ],
                    ),
                    (
                        "System",
                        [
                            (
                                "Company Profile", "Set the company name, address, and GSTIN printed on receipts and reports.",
                                lambda: SettingsWindow(self._settings_service, self._user_data["id"], self._auth_service),
                                Permission.SETTINGS_VIEW,
                            ),
                        ],
                    ),
                ],
            ),
            (
                "OPERATIONS",
                [
                    (
                        "Sales & Shifts",
                        [
                            (
                                "Terminal", "Fast fuel-sale entry at the pump during a live shift.",
                                lambda: TerminalWindow(
                                    self._sale_service, self._shift_service, self._employee_service, self._auth_service, self._user_data["id"]
                                ),
                                Permission.SALE_MANAGE,
                            ),
                            (
                                "Sales", "Look up past sales and manage customer records.",
                                lambda: SalesWindow(
                                    self._sale_service, self._shift_service, self._employee_service,
                                    self._auth_service, self._user_data["id"], self._report_service,
                                ),
                                Permission.SALE_VIEW,
                            ),
                            (
                                "Shifts", "Open and close shifts, and assign attendants to nozzles.",
                                lambda: ShiftListWindow(
                                    self._shift_service, self._employee_service, self._auth_service, self._user_data["id"]
                                ),
                                Permission.SHIFT_VIEW,
                            ),
                            (
                                "My Shift", "See your own current nozzle and fuel assignment.",
                                lambda: MyShiftWindow(self._shift_service, self._auth_service, self._user_data["id"]),
                                Permission.MY_ASSIGNMENT_VIEW,
                            ),
                            (
                                "Attendance", "Mark today's attendance and review past records.",
                                lambda: AttendanceWindow(
                                    self._attendance_service,
                                    self._employee_service,
                                    self._shift_service,
                                    self._auth_service,
                                    self._user_data["id"],
                                ),
                                Permission.ATTENDANCE_VIEW,
                            ),
                            (
                                "Leave", "Request leave on an employee's behalf and approve or reject requests.",
                                lambda: LeaveWindow(
                                    self._leave_service, self._employee_service, self._auth_service, self._user_data["id"]
                                ),
                                Permission.LEAVE_VIEW,
                            ),
                        ],
                    ),
                    (
                        "Money",
                        [
                            (
                                "Credit", "Open credit accounts, record customer payments, and track balances.",
                                lambda: CreditWindow(self._credit_service, self._sale_service, self._auth_service, self._user_data["id"]),
                                Permission.CREDIT_VIEW,
                            ),
                            (
                                "Expenses", "Record pump expenses and approve the ones awaiting sign-off.",
                                lambda: ExpenseWindow(
                                    self._expense_service, self._employee_service, self._shift_service, self._auth_service, self._user_data["id"]
                                ),
                                Permission.EXPENSE_VIEW,
                            ),
                            (
                                "Reconciliation", "Reconcile cash, UPI, and card totals against each shift.",
                                lambda: ReconciliationWindow(
                                    self._reconciliation_service, self._shift_service, self._auth_service, self._user_data["id"],
                                    cash_book_service=self._cash_book_service,
                                    employee_shortage_service=self._employee_shortage_service,
                                    employee_service=self._employee_service,
                                ),
                                Permission.RECONCILIATION_VIEW,
                            ),
                        ],
                    ),
                    (
                        "Procurement",
                        [
                            (
                                "Procurement", "Raise purchase orders, receive deliveries, and record supplier invoices.",
                                lambda: ProcurementWindow(
                                    self._procurement_service, self._fuel_repo, self._tank_service,
                                    self._employee_service, self._auth_service, self._user_data["id"], initial_tab=1,
                                ),
                                Permission.PROCUREMENT_VIEW,
                            ),
                        ],
                    ),
                ],
            ),
            (
                "SETTINGS",
                [
                    (
                        "Administration",
                        [
                            (
                                "Backups", "Back up the database now, or restore from an earlier backup.",
                                lambda: BackupWindow(self._backup_service, self._user_data["id"], self._settings_service),
                                Permission.BACKUP_MANAGE,
                            ),
                            (
                                "Audit Log", "Review every recorded change, by whom and when.",
                                lambda: AuditLogWindow(self._audit_service, self._user_repo, self._user_data["id"]),
                                Permission.AUDIT_VIEW,
                            ),
                        ],
                    ),
                ],
            ),
        ]
        # Reports' own multi-permission gate (any of these lets the group
        # row show at all - ReportsHubWindow gates each report inside it
        # individually the same way it always has).
        self._reports_permissions = (
            Permission.INVENTORY_VIEW, Permission.SALE_VIEW, Permission.EXPENSE_VIEW,
            Permission.CREDIT_VIEW, Permission.RECONCILIATION_VIEW, Permission.ANALYTICS_VIEW,
        )
        self._stat_tiles = self._build_stat_tiles(user_data["id"])
        self._dashboard_columns = 0  # forces the first _populate_dashboard call to actually build

        # Two independent dynamic blocks, not one, so the build-once
        # sections below (alerts, chart, roster) can sit BETWEEN them in
        # the page's reading order while both still individually reflow
        # their own column count on resize (see resizeEvent/_populate_dashboard).
        self._stats_layout = QVBoxLayout()
        self._stats_layout.setSpacing(28)
        self._tank_gauges_layout = QVBoxLayout()
        self._tank_gauges_layout.setSpacing(28)

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(DASHBOARD_PAGE_MARGIN, DASHBOARD_PAGE_MARGIN, DASHBOARD_PAGE_MARGIN, DASHBOARD_PAGE_MARGIN)
        body_layout.setSpacing(28)
        body_layout.addLayout(header_layout)
        body_layout.addLayout(self._stats_layout)

        # Every section from here down is built once (not inside
        # _populate_dashboard, which clears and rebuilds the two layouts
        # above on every column-count change during a resize) so resizing
        # the window never re-fetches or re-renders their data - same
        # reasoning _stat_tiles is computed once in __init__ rather than
        # inside _populate_dashboard.
        alerts_section = self._build_alerts_section(user_data["id"])
        if alerts_section is not None:
            body_layout.addWidget(alerts_section)

        if self._is_card_visible(Permission.SALE_VIEW):
            from app.ui.widgets import SalesTrendChart

            chart_card = QWidget()
            chart_card.setObjectName("card")
            chart_card.setAttribute(Qt.WA_StyledBackground, True)
            chart_layout = QVBoxLayout()
            chart_layout.setContentsMargins(20, 16, 20, 16)
            chart_layout.addWidget(
                SalesTrendChart(lambda days: self._dashboard_service.get_recent_daily_sales(user_data["id"], days))
            )
            chart_card.setLayout(chart_layout)
            apply_hard_shadow(chart_card)
            body_layout.addWidget(chart_card)

        body_layout.addLayout(self._tank_gauges_layout)

        roster_section = self._build_shift_roster_section(user_data["id"])
        if roster_section is not None:
            body_layout.addWidget(roster_section)

        body_layout.addStretch()

        body = GridBackgroundWidget()
        body.setObjectName("background")
        body.setLayout(body_layout)

        # A QScrollArea, not a bare widget, so the dashboard stays usable
        # (scrolls instead of clipping) on a small window or a role with
        # enough visible cards to overflow a short screen - part of
        # making the dashboard genuinely responsive, not just the card
        # grid's column count.
        scroll = QScrollArea()
        scroll.setObjectName("background")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        self._dashboard_page = scroll

        # A breadcrumb strip sits between the top bar and whatever is
        # currently on screen. It is hidden on the dashboard itself and
        # appears the moment a module page is open, giving the operator
        # a "Back" affordance and a sense of where they are - the same
        # job a browser's back button + tab title used to do implicitly
        # when every module was its own separate window.
        self._back_button = QPushButton("← Back")
        self._back_button.setObjectName("secondaryButton")
        self._back_button.setCursor(Qt.PointingHandCursor)
        self._back_button.setToolTip("Back (Esc)")
        self._back_button.clicked.connect(self._go_back)

        # Every segment but the last is a clickable link straight to that
        # level (e.g. clicking "Reports" from "Reports > Sales Report"
        # jumps back to the hub in one step); rebuilt on every navigation
        # since its length depends on how deep the operator has drilled.
        self._breadcrumb_segments_layout = QHBoxLayout()
        self._breadcrumb_segments_layout.setSpacing(6)

        breadcrumb_layout = QHBoxLayout()
        breadcrumb_layout.setContentsMargins(DASHBOARD_PAGE_MARGIN, 10, DASHBOARD_PAGE_MARGIN, 10)
        breadcrumb_layout.setSpacing(12)
        breadcrumb_layout.addWidget(self._back_button)
        breadcrumb_layout.addLayout(self._breadcrumb_segments_layout)
        breadcrumb_layout.addStretch()

        self._breadcrumb_bar = QWidget()
        self._breadcrumb_bar.setObjectName("breadcrumbBar")
        self._breadcrumb_bar.setLayout(breadcrumb_layout)
        self._breadcrumb_bar.setVisible(False)

        # Every module page (created lazily, on first visit) lives here
        # instead of as its own top-level QMainWindow - index 0 is
        # permanently the dashboard; _open_module_page/_push_subpage add
        # and remove the rest as the operator navigates.
        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(scroll)

        from app.ui.alert_strip import AlertStrip

        # Always visible above the content area, never hidden behind a
        # click (Part B, 2026-09-16) - a sibling of top_bar/breadcrumb_bar/
        # content_stack in this same layout, not something an individual
        # module page owns, so it stays on screen no matter which page is
        # open. Built empty here (no data fetch - see AlertStrip's own
        # docstring for the documented crash that constraint avoids) and
        # populated by the same deferred timer tick that already fills in
        # the Alerts button's badge; see refresh_alert_badge.
        self._alert_strip = AlertStrip(on_navigate=self._navigate_to_notification)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(top_bar)
        content_layout.addWidget(self._alert_strip)
        content_layout.addWidget(self._breadcrumb_bar)
        content_layout.addWidget(self._content_stack, stretch=1)

        content_column = QWidget()
        content_column.setLayout(content_layout)

        self._sidebar = Sidebar(
            app_name="Petrol Pump ERP",
            device_label=platform.node() or "unknown-device",
            nav_groups=[
                ("Masters", self._open_masters_landing, self._group_permissions("MASTERS")),
                ("Operations", self._open_operations_landing, self._group_permissions("OPERATIONS")),
                ("Reports", self._open_reports, self._reports_permissions),
                ("Settings", self._open_settings_landing, self._group_permissions("SETTINGS")),
            ],
            is_card_visible=self._is_card_visible,
            home_action=("Dashboard", self._go_home),
            footer_actions=[
                ("Support", self._open_support),
                ("Change Password", self._open_change_password),
                ("Logout", self._logout),
            ],
        )
        self._sidebar.set_active("Dashboard")

        outer_layout = QHBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._sidebar)
        outer_layout.addWidget(content_column, stretch=1)

        container = QWidget()
        container.setLayout(outer_layout)
        self.setCentralWidget(container)

        self._install_keyboard_shortcuts()

        self._populate_dashboard(self._compute_card_columns())
        # The alert count is deliberately NOT computed here, and the two
        # earlier attempts are recorded because the reasoning is not
        # obvious from the result.
        #
        # Computing it inside __init__ crashed the interpreter: a garbage
        # collection landing inside SQLAlchemy's result processing while
        # a freshly-built Qt widget tree was still settling. Deferring it
        # with QTimer.singleShot(0, ...) only moved the crash, because
        # the callback then ran while that same widget tree was becoming
        # garbage. Reducing it to a SINGLE trivial query crashed too -
        # which is what proved the problem is not the amount of work but
        # the moment: database work does not belong near Qt widget
        # construction or teardown in this application.
        #
        # So the badge is filled in from the session tick that already
        # runs every 60 seconds against a settled, idle window, and
        # refreshed again whenever the Alerts screen is opened. The cost
        # is a blank count for up to a minute after login; the benefit is
        # that refreshing periodically is what a live indicator should do
        # anyway, rather than taking one reading at login and letting it
        # go stale for the rest of the shift.

        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._check_session)
        self._session_timer.start(SESSION_CHECK_INTERVAL_MS)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        columns = self._compute_card_columns()
        if columns != self._dashboard_columns:
            self._populate_dashboard(columns)

    def _compute_card_columns(self) -> int:
        return compute_dashboard_columns(self.width() - SIDEBAR_WIDTH)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Removing a widget from a layout does not hide it - it
                # stays painted at its last position/size until Qt gets
                # around to processing the deferred deleteLater(), which
                # can be a visible frame or two later. Hiding it here,
                # synchronously, is what actually stops it from being
                # drawn - deleteLater() alone only reclaims the memory.
                widget.hide()
                widget.deleteLater()
                continue
            child_layout = item.layout()
            if child_layout is not None:
                MainWindow._clear_layout(child_layout)

    def _is_card_visible(self, permission) -> bool:
        """Shared by both the sidebar's nav items and the dashboard's own
        quick-access card grid, so the two can never show a different set
        of modules to the same logged-in user."""
        permissions = permission if isinstance(permission, tuple) else (permission,)
        return any(self._auth_service.check_permission(self._user_data["id"], p.value) for p in permissions)

    def _group_permissions(self, label: str) -> list:
        """Every permission (or permission tuple) belonging to one
        _card_groups group, flattened across its subheadings - used only
        to decide whether that group's sidebar row should show at all."""
        subgroups = next(items for group_label, items in self._card_groups if group_label == label)
        return [permission for _subheading, entries in subgroups for *_rest, permission in entries]

    def _populate_dashboard(self, columns: int) -> None:
        """Rebuilds the two column-count-dependent sections (stat tiles,
        tank gauges) whenever the window is resized across a column-count
        threshold - see resizeEvent. Every other dashboard section
        (alerts, sales chart, shift roster) is content that doesn't
        reflow by column, so it's built once in __init__ instead; see the
        comment there for why that split matters for a resize's cost.

        Quick-access module tiles used to live here too, duplicating the
        sidebar's own navigation one scroll below it - removed 2026-08-26
        so this space goes to the sidebar's sole job (navigation) and the
        dashboard's own job (a live snapshot of the business), rather than
        overlapping between the two.
        """
        self._dashboard_columns = columns
        self._clear_layout(self._stats_layout)
        self._clear_layout(self._tank_gauges_layout)

        if self._stat_tiles:
            stat_columns = min(len(self._stat_tiles), max(columns, 1))
            stats_grid = QGridLayout()
            stats_grid.setSpacing(16)
            for column in range(stat_columns):
                stats_grid.setColumnStretch(column, 1)
            for index, (value, label, tone) in enumerate(self._stat_tiles):
                row, column = divmod(index, stat_columns)
                stats_grid.addWidget(StatCard(value, label, tone), row, column)
            self._stats_layout.addLayout(stats_grid)

        if self._is_card_visible(Permission.INVENTORY_VIEW):
            try:
                tanks = self._tank_service.list_tanks(self._user_data["id"])
            except Exception as exc:  # noqa: BLE001 - the dashboard must still load if tank data can't be fetched
                describe_unexpected_error(exc)
                tanks = []

            if tanks:
                tank_label = QLabel("LIVE TANK LEVELS")
                tank_label.setObjectName("dashGroupLabel")

                tank_columns = max(1, min(columns, DASHBOARD_TANK_GAUGE_MAX_COLUMNS))
                tank_grid = QGridLayout()
                tank_grid.setSpacing(16)
                for column in range(tank_columns):
                    tank_grid.setColumnStretch(column, 1)
                for index, tank in enumerate(tanks):
                    row, column = divmod(index, tank_columns)
                    tank_grid.addWidget(
                        TankGaugeCard(
                            tank.code,
                            tank.fuel.fuel_type if tank.fuel else "",
                            tank.status,
                            tank.current_stock,
                            tank.capacity,
                        ),
                        row,
                        column,
                    )

                tank_section = QVBoxLayout()
                tank_section.setSpacing(10)
                tank_section.addWidget(tank_label)
                tank_section.addLayout(tank_grid)
                self._tank_gauges_layout.addLayout(tank_section)

    def _build_alerts_section(self, actor_user_id: str) -> QWidget | None:
        """The top few live alerts, inline on the dashboard rather than
        behind only the Alerts button - reuses NotificationService and
        AlertCard exactly as the Alerts screen itself does (see
        notification_window.py), so this can never disagree with that
        screen about which alerts exist or how they're worded. Returns
        None only when even the "all clear" line can't be shown (the
        summary call itself failed) - the dashboard must still load.
        """
        from app.ui.notification_window import AlertCard

        try:
            summary = self._notification_service.get_notifications(actor_user_id)
        except Exception as exc:  # noqa: BLE001 - the dashboard must still load if alerts can't be computed
            describe_unexpected_error(exc)
            return None

        label = QLabel("ATTENTION NEEDED")
        label.setObjectName("dashGroupLabel")

        section_layout = QVBoxLayout()
        section_layout.setSpacing(12)
        section_layout.addWidget(label)

        if summary.total == 0:
            all_clear = QLabel("All clear — nothing needs attention right now.")
            all_clear.setObjectName("subtitle")
            section_layout.addWidget(all_clear)
        else:
            # is_summary lines are NotificationService's own "N more of
            # this category" trailers - skipped here since the dashboard
            # has its own "view all" link below instead of a second,
            # differently-worded overflow note.
            shown = [n for n in summary.notifications if not n.is_summary][:ALERTS_SHOWN_ON_DASHBOARD]
            for notification in shown:
                section_layout.addWidget(AlertCard(notification))

            view_all = QPushButton(f"View all {summary.total} alerts →")
            view_all.setObjectName("secondaryButton")
            view_all.setCursor(Qt.PointingHandCursor)
            view_all.clicked.connect(self._open_notifications)
            link_row = QHBoxLayout()
            link_row.addWidget(view_all)
            link_row.addStretch()
            section_layout.addLayout(link_row)

        wrapper = QWidget()
        wrapper.setLayout(section_layout)
        return wrapper

    def _build_shift_roster_section(self, actor_user_id: str) -> QWidget | None:
        """Who is actually on a nozzle right now, across every shift open
        today - replaces the old "shifts open now" stat tile's bare count
        with the roster behind it, the same employee/nozzle/fuel data the
        Shifts screen's own assignment view already shows (ShiftService,
        not a duplicated query). Gated on SHIFT_VIEW like every other
        shift figure on this page; returns None (no card at all) for a
        role that cannot see shifts, rather than an empty card.
        """
        if not self._is_card_visible(Permission.SHIFT_VIEW):
            return None

        try:
            todays_shifts = self._shift_service.list_shifts(actor_user_id, date.today(), date.today())
        except Exception as exc:  # noqa: BLE001 - the dashboard must still load if the roster can't be fetched
            describe_unexpected_error(exc)
            todays_shifts = []

        rows: list[tuple[str, str]] = []
        for shift in todays_shifts:
            if shift.status != ShiftStatus.OPEN.value:
                continue
            for assignment in shift.nozzle_assignments:
                if assignment.status != AssignmentStatus.ACTIVE.value:
                    continue
                employee = assignment.employee
                name = f"{employee.first_name} {employee.last_name}" if employee else "Unknown employee"
                nozzle_code = assignment.nozzle.code if assignment.nozzle else "?"
                fuel_type = assignment.nozzle.fuel.fuel_type if assignment.nozzle and assignment.nozzle.fuel else ""
                since = assignment.start_time.strftime("%H:%M") if assignment.start_time else "—"
                rows.append((name, f"{nozzle_code} · {fuel_type} · {shift.shift_label} · since {since}"))
        rows.sort(key=lambda row: row[0])

        title = QLabel(f"On Shift Now ({len(rows)})" if rows else "On Shift Now")
        title.setObjectName("sectionTitle")

        inner = QVBoxLayout()
        inner.setContentsMargins(20, 18, 20, 18)
        inner.setSpacing(14)
        inner.addWidget(title)

        if not rows:
            empty = QLabel("No attendant is currently assigned to a nozzle.")
            empty.setObjectName("subtitle")
            empty.setWordWrap(True)
            inner.addWidget(empty)
        else:
            rows_layout = QVBoxLayout()
            rows_layout.setSpacing(12)
            for name, detail in rows[:ROSTER_ROWS_SHOWN_ON_DASHBOARD]:
                name_label = QLabel(name)
                name_label.setObjectName("dashCardTitle")
                detail_label = QLabel(detail)
                detail_label.setObjectName("subtitle")
                row_layout = QVBoxLayout()
                row_layout.setSpacing(2)
                row_layout.addWidget(name_label)
                row_layout.addWidget(detail_label)
                rows_layout.addLayout(row_layout)
            inner.addLayout(rows_layout)

            overflow = len(rows) - ROSTER_ROWS_SHOWN_ON_DASHBOARD
            if overflow > 0:
                more = QLabel(f"+{overflow} more on shift")
                more.setObjectName("subtitle")
                inner.addWidget(more)

        panel = QWidget()
        panel.setObjectName("card")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel.setLayout(inner)
        apply_hard_shadow(panel)
        return panel

    def _build_stat_tiles(self, actor_user_id: str) -> list[tuple[str, str, str]]:
        try:
            summary = self._dashboard_service.get_summary(actor_user_id)
        except Exception as exc:  # noqa: BLE001 - a KPI strip must never block the dashboard from loading
            describe_unexpected_error(exc)
            return []

        tiles: list[tuple[str, str, str]] = []
        if summary.sales_today_count is not None:
            tiles.append((str(summary.sales_today_count), "Sales today", "normal"))
            tiles.append((f"₹{summary.sales_today_amount:,.2f}", "Revenue today", "normal"))
        if summary.open_shifts_count is not None:
            tiles.append((str(summary.open_shifts_count), "Shifts open now", "normal"))
        if summary.low_stock_tanks_count is not None:
            tone = "warning" if summary.low_stock_tanks_count > 0 else "normal"
            tiles.append((str(summary.low_stock_tanks_count), "Tanks running low", tone))
        if summary.pending_purchase_orders_count is not None:
            tiles.append((str(summary.pending_purchase_orders_count), "Purchase orders pending", "normal"))
        return tiles

    def refresh_alert_badge(self) -> None:
        """Update the top-bar Alerts button's count and colour.

        Failure is swallowed and the button falls back to a plain "Alerts"
        label. The alert count is an aid, not a gate: a dashboard that
        refuses to load because a badge query failed would be a far worse
        outcome than a badge that is briefly missing - the same reasoning
        already applied to the KPI strip in _build_stat_tiles.
        """
        # Belt and braces alongside the timer's context binding: this can
        # also be reached from the session timer, and querying the
        # database on behalf of a window that no longer exists is work
        # whose result has nowhere to go.
        if not is_widget_alive(self):
            return

        try:
            summary = self._notification_service.get_notifications(self._user_data["id"])
        except Exception:  # noqa: BLE001
            self.alerts_button.setText("Alerts")
            self._set_alert_tone("")
            self._alert_strip.set_summary(None)
            return

        # One fetch, two consumers (the badge here and the persistent
        # strip) - the strip is the alert screen's THIRD consumer of this
        # same NotificationService call (after the dashboard's own
        # "Attention Needed" section and the Alerts dropdown), never a
        # separate query.
        self._alert_strip.set_summary(summary)

        if summary.total == 0:
            self.alerts_button.setText("Alerts")
            self._set_alert_tone("")
            return

        self.alerts_button.setText(f"Alerts ({summary.total})")
        # The badge takes the colour of the WORST thing in the list, not
        # the most common one - the point of the tone is to say whether
        # anything here cannot wait.
        if summary.critical_count:
            self._set_alert_tone("critical")
        elif summary.warning_count:
            self._set_alert_tone("warning")
        else:
            self._set_alert_tone("")

    def refresh_shift_indicator(self) -> None:
        """Update the top-bar current-shift indicator (problemstatement.md
        #37/#36). Same "an aid, not a gate" reasoning as refresh_alert_badge
        and _build_stat_tiles: a failed or unauthorized query degrades to
        a neutral label rather than blocking anything."""
        if not is_widget_alive(self):
            return

        try:
            summary = self._dashboard_service.get_summary(self._user_data["id"])
        except Exception:  # noqa: BLE001
            self.shift_indicator_label.setText("Shift: —")
            self._set_shift_tone("")
            return

        labels = summary.open_shift_labels
        if labels is None:
            # SHIFT_VIEW not held by this role (e.g. an attendant only
            # sees their own assignment via My Shift) - nothing useful to
            # show, so the indicator hides rather than displaying a
            # confusing dash.
            self.shift_indicator_label.hide()
            return

        self.shift_indicator_label.show()
        if not labels:
            self.shift_indicator_label.setText("No shift open")
            self._set_shift_tone("")
        elif len(labels) == 1:
            self.shift_indicator_label.setText(f"Shift: {labels[0]} • Open")
            self._set_shift_tone("open")
        else:
            self.shift_indicator_label.setText(f"{len(labels)} shifts open")
            self._set_shift_tone("open")

    def _set_shift_tone(self, tone: str) -> None:
        """Same unpolish/polish dance as _set_alert_tone - Qt does not
        restyle a widget on its own when a stylesheet-selector property
        changes after the widget is already shown."""
        self.shift_indicator_label.setProperty("tone", tone)
        self.shift_indicator_label.style().unpolish(self.shift_indicator_label)
        self.shift_indicator_label.style().polish(self.shift_indicator_label)

    def _set_alert_tone(self, tone: str) -> None:
        """Qt does not restyle a widget when a property used in a
        stylesheet selector changes, so the style has to be explicitly
        unpolished and repolished - otherwise the colour would only ever
        be whatever it was when the widget was first shown."""
        self.alerts_button.setProperty("tone", tone)
        self.alerts_button.style().unpolish(self.alerts_button)
        self.alerts_button.style().polish(self.alerts_button)

    def _open_notifications(self) -> None:
        from app.ui.notification_window import NotificationWindow

        try:
            # Alerts has no sidebar row of its own (it's reached from the
            # always-visible top-bar button, not a module card), so it
            # gets a plain key with nothing to highlight.
            self._open_module_page(
                "Alerts", lambda: NotificationWindow(self._notification_service, self._user_data["id"])
            )
            self._sidebar.set_active(None)
            # Opening the screen is also the natural moment to re-sync the
            # badge, since the window has just recomputed the same list.
            self.refresh_alert_badge()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not open alerts", describe_unexpected_error(exc))

    # Category -> (group, the exact module tile to open). Deliberately a
    # screen, not a specific row within it: going further (e.g. opening
    # Tanks with the exact low tank's detail dialog already showing)
    # would mean threading a "focus on this record" parameter through
    # several more module windows, which is module-internals work this
    # pass was explicitly scoped to avoid (see PROJECT_CONTEXT.md,
    # 2026-09-16) - recorded as a follow-up, not silently dropped.
    _NOTIFICATION_TARGETS = {
        NotificationCategory.LOW_FUEL: ("MASTERS", "Tanks"),
        NotificationCategory.FUEL_VARIANCE: ("MASTERS", "Tanks"),
        NotificationCategory.CASH_SHORTAGE: ("OPERATIONS", "Reconciliation"),
        NotificationCategory.CASH_EXCESS: ("OPERATIONS", "Reconciliation"),
        NotificationCategory.PAYMENT_MISMATCH: ("OPERATIONS", "Reconciliation"),
        NotificationCategory.FAILED_RECONCILIATION: ("OPERATIONS", "Reconciliation"),
        NotificationCategory.ATTENDANCE_ISSUE: ("OPERATIONS", "Attendance"),
        NotificationCategory.OUTSTANDING_CREDIT: ("OPERATIONS", "Credit"),
        NotificationCategory.SUPPLIER_PAYMENT_DUE: ("OPERATIONS", "Procurement"),
        NotificationCategory.UNAUTHORIZED_ACTION: ("SETTINGS", "Audit Log"),
        NotificationCategory.DATABASE_ERROR: ("SETTINGS", "Audit Log"),
        NotificationCategory.BACKUP_FAILURE: ("SETTINGS", "Backups"),
    }

    def _find_module_factory(self, group_label: str, item_title: str):
        """Looks up one module's window factory straight out of
        _card_groups by (group, title) - the alert strip's click-to-
        navigate reuses the exact same factories the landing pages
        render as tiles, never a second list of "how to open X"."""
        subgroups = next(items for label, items in self._card_groups if label == group_label)
        for _subheading, entries in subgroups:
            for title, _subtitle, factory, _permission in entries:
                if title == item_title:
                    return factory
        return None

    def _navigate_to_notification(self, notification) -> None:
        """The alert strip's click-to-navigate: opens the exact screen
        an alert is about, not just the general dashboard. Named apart
        from the _open_* family on purpose - it takes a required
        argument, so it must not be swept up by the reflection-based
        "call every _open_* opener with no arguments" tests in
        test_main_window_open_paths.py. PENDING_APPROVAL
        covers two different screens (expenses and reconciliation), so it
        is resolved from the notification's own title rather than a
        single fixed target."""
        if notification.category == NotificationCategory.PENDING_APPROVAL:
            target = ("OPERATIONS", "Expenses" if "expense" in notification.title.lower() else "Reconciliation")
        else:
            target = self._NOTIFICATION_TARGETS.get(notification.category)
        if target is None:
            return

        group_label, item_title = target
        factory = self._find_module_factory(group_label, item_title)
        if factory is None:
            return

        group_openers = {
            "MASTERS": self._open_masters_landing,
            "OPERATIONS": self._open_operations_landing,
            "SETTINGS": self._open_settings_landing,
        }
        # Opens the real landing page first (exactly the page a click on
        # the sidebar group would show) and then drills in - the same
        # two-step path a user's own click takes, so the breadcrumb reads
        # "Masters > Tanks" and Back returns to the landing page, not a
        # shortcut that skips straight to the module with no way back.
        group_openers[group_label]()
        self._push_subpage(item_title, factory)

    def _check_session(self) -> None:
        try:
            self._auth_service.validate_session(self._session_token)
        except SessionExpiredError:
            self._session_timer.stop()
            QMessageBox.information(self, "Session expired", "Your session has expired. Please log in again.")
            self.logout_requested.emit(True)
            return
        except Exception as exc:  # noqa: BLE001 - a periodic timer callback must never crash the app
            describe_unexpected_error(exc)
            return

        # Piggy-backed on the session tick rather than given a timer of
        # its own: the session is still valid, the window is settled and
        # idle, and this is exactly the safe moment for database work
        # (see the note in __init__ about why it cannot happen earlier).
        # One timer also means one place where periodic work happens,
        # instead of two competing schedules.
        self.refresh_alert_badge()
        self.refresh_shift_indicator()

    def _logout(self) -> None:
        self._session_timer.stop()
        try:
            self._auth_service.logout(self._session_token)
        except Exception as exc:  # noqa: BLE001 - still return the user to the login screen even if this fails
            describe_unexpected_error(exc)
        self.logout_requested.emit(False)

    # ------------------------------------------------------------------
    # Embedded-page navigation
    #
    # Every module used to be its own top-level QMainWindow, created
    # fresh and handed to .show() on every click - a real OS window the
    # operator then had to find, arrange, and close by hand, and one
    # that could just as easily get lost behind the main window. All of
    # that now lives inside self._content_stack instead. The dashboard
    # (index 0) never leaves the stack; every module page is added on
    # demand and thrown away (deleteLater) the moment the operator
    # navigates elsewhere, so each visit still gets a fresh instance
    # querying live data - exactly the behaviour the old "always
    # construct a new window" pattern gave for free.
    # ------------------------------------------------------------------

    def _open_module_page(self, key: str, factory) -> None:
        """Entry point for a sidebar/dashboard-card click: replaces
        whatever is currently open (including any drill-down pushed on
        top of it) with a single fresh top-level module page."""
        self._clear_page_stack()
        widget = factory()
        self._content_stack.addWidget(widget)
        self._content_stack.setCurrentWidget(widget)
        self._page_stack = [(widget, key, key)]
        self._sidebar.set_active(key)
        self._update_breadcrumb()

    def _push_subpage(self, title: str, factory) -> None:
        """Called by a hub page (e.g. Reports) to drill into a detail
        page while leaving the hub itself one step back - the embedded
        equivalent of the hub opening a second popup window on top of
        itself."""
        widget = factory()
        self._content_stack.addWidget(widget)
        self._content_stack.setCurrentWidget(widget)
        self._page_stack.append((widget, title, None))
        self._update_breadcrumb()

    @staticmethod
    def _remove_page(content_stack, widget) -> None:
        """Removes and schedules deletion of one page. QStackedWidget's
        own removeWidget() does NOT clear the page's Qt parent - it stays
        a real child of the stack (confirmed directly: even several
        processEvents() calls after removeWidget()+deleteLater() alone
        never destroy it, since a still-parented object is never actually
        idle-collected) - the same behaviour _clear_layout's own comment
        already documents for a plain layout removal. Without the
        explicit setParent(None) here, every module a user ever navigates
        away from stays alive and parented to _content_stack forever:
        found via test_opening_the_same_module_twice_leaves_only_one_
        instance_embedded, which kept finding old instances still in the
        widget tree (2026-09-16)."""
        content_stack.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()

    def _install_keyboard_shortcuts(self) -> None:
        """problemstatement.md #37: "Keyboard shortcuts... Minimal clicks...
        Fast data entry" - this app is used standing at a busy forecourt
        counter, not at a desk, so reaching for the mouse for routine
        moves (find a record, refresh a list, step back a screen) costs
        real time across a whole shift. Three shortcuts, each a standard,
        widely-known convention rather than something invented for this
        app specifically - matching an existing convention costs a user
        nothing to learn, unlike a bespoke binding they'd have to be
        taught.

        Every QShortcut here defaults to Qt.WindowShortcut context, so it
        only fires while this window (or a non-modal child of it) has
        focus - a separate modal QDialog (e.g. the forced change-password
        dialog, or a confirmation box) is its own top-level window and is
        unaffected, exactly as it should be.
        """
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search_shortcut)
        QShortcut(QKeySequence("F5"), self, activated=self._refresh_active_page_shortcut)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._go_back_shortcut)

    def _focus_search_shortcut(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _refresh_active_page_shortcut(self) -> None:
        """Calls the open page's own refresh() - the same method its
        on-screen Refresh button already calls - if it has one. Plain
        pages with nothing to reload (e.g. Settings) simply have no such
        method, so this is a safe no-op there rather than something that
        needs a lookup table of which pages support it."""
        page = self._content_stack.currentWidget()
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    def _go_back_shortcut(self) -> None:
        # A text field's own Escape handling (e.g. closing the search
        # box's completer popup) should win over navigating away - only
        # step back when focus isn't in a text-entry widget, so Escape
        # never yanks a supervisor mid-typing off the screen they're on.
        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QComboBox)):
            return
        self._go_back()

    def _go_back(self) -> None:
        if not self._page_stack:
            return
        widget, _title, _key = self._page_stack.pop()
        self._remove_page(self._content_stack, widget)
        if not self._page_stack:
            self._go_home()
            return
        self._content_stack.setCurrentWidget(self._page_stack[-1][0])
        self._sidebar.set_active(self._page_stack[0][2])
        self._update_breadcrumb()

    def _jump_to(self, index: int) -> None:
        """Clicking a non-final breadcrumb segment jumps straight to that
        level in one step, instead of clicking Back repeatedly."""
        if index >= len(self._page_stack) - 1:
            return
        for widget, _title, _key in self._page_stack[index + 1 :]:
            self._remove_page(self._content_stack, widget)
        self._page_stack = self._page_stack[: index + 1]
        self._content_stack.setCurrentWidget(self._page_stack[-1][0])
        self._sidebar.set_active(self._page_stack[0][2])
        self._update_breadcrumb()

    def _go_home(self) -> None:
        self._clear_page_stack()
        self._content_stack.setCurrentWidget(self._dashboard_page)
        self._sidebar.set_active("Dashboard")
        self._breadcrumb_bar.setVisible(False)

    def _clear_page_stack(self) -> None:
        for widget, _title, _key in self._page_stack:
            self._remove_page(self._content_stack, widget)
        self._page_stack = []

    def _update_breadcrumb(self) -> None:
        self._clear_layout(self._breadcrumb_segments_layout)

        if not self._page_stack:
            self._breadcrumb_bar.setVisible(False)
            return
        self._breadcrumb_bar.setVisible(True)

        last_index = len(self._page_stack) - 1
        for index, (_widget, title, _key) in enumerate(self._page_stack):
            if index == last_index:
                segment = QLabel(title)
                segment.setObjectName("breadcrumbLabel")
            else:
                segment = QPushButton(title)
                segment.setObjectName("breadcrumbLink")
                segment.setCursor(Qt.PointingHandCursor)
                segment.clicked.connect(lambda _checked=False, i=index: self._jump_to(i))
            self._breadcrumb_segments_layout.addWidget(segment)

            if index != last_index:
                separator = QLabel("›")
                separator.setObjectName("breadcrumbSeparator")
                self._breadcrumb_segments_layout.addWidget(separator)

    def _open_masters_landing(self) -> None:
        """Opens the Masters group's landing page - see _card_groups for
        the tiles it renders and group_landing_window.py for the page
        itself. Individual modules (Employees, Tanks, ...) have no
        sidebar row or _open_* method of their own any more; they are
        reached one level down, by clicking a tile here."""
        from app.ui.group_landing_window import GroupLandingWindow

        subgroups = next(items for label, items in self._card_groups if label == "MASTERS")
        self._open_module_page(
            "Masters",
            lambda: GroupLandingWindow(
                "Masters",
                "Reference data used across every other module - staff, logins, suppliers, fuel, tanks, and nozzles.",
                subgroups,
                self._is_card_visible,
                open_subpage=self._push_subpage,
            ),
        )

    def _open_operations_landing(self) -> None:
        """Opens the Operations group's landing page - see _card_groups
        and _open_masters_landing's docstring for the pattern."""
        from app.ui.group_landing_window import GroupLandingWindow

        subgroups = next(items for label, items in self._card_groups if label == "OPERATIONS")
        self._open_module_page(
            "Operations",
            lambda: GroupLandingWindow(
                "Operations",
                "The day-to-day business: sales, shifts, money in and out, and procurement.",
                subgroups,
                self._is_card_visible,
                open_subpage=self._push_subpage,
            ),
        )

    def _open_settings_landing(self) -> None:
        """Opens the Settings group's landing page - see _card_groups
        and _open_masters_landing's docstring for the pattern."""
        from app.ui.group_landing_window import GroupLandingWindow

        subgroups = next(items for label, items in self._card_groups if label == "SETTINGS")
        self._open_module_page(
            "Settings",
            lambda: GroupLandingWindow(
                "Settings",
                "System administration and maintenance - not day-to-day business data.",
                subgroups,
                self._is_card_visible,
                open_subpage=self._push_subpage,
            ),
        )

    def _open_reports(self) -> None:
        from app.ui.report_window import ReportsHubWindow

        self._open_module_page(
            "Reports",
            lambda: ReportsHubWindow(
                self._report_service,
                self._auth_service,
                self._user_data["id"],
                self._analytics_service,
                open_subpage=self._push_subpage,
            ),
        )

    def _open_users(self) -> None:
        from app.ui.user_management_window import UserListWindow

        self._open_module_page(
            "Users",
            lambda: UserListWindow(self._user_service, self._role_repo, self._user_data["id"]),
        )

    def _open_backups(self) -> None:
        from app.ui.backup_window import BackupWindow

        self._open_module_page(
            "Backups",
            lambda: BackupWindow(self._backup_service, self._user_data["id"], self._settings_service),
        )

    def _open_audit_log(self) -> None:
        from app.ui.audit_log_window import AuditLogWindow

        self._open_module_page(
            "Audit Log",
            lambda: AuditLogWindow(self._audit_service, self._user_repo, self._user_data["id"]),
        )

    def _open_support(self) -> None:
        from app.ui.support_window import SupportWindow

        # No sidebar row of its own (it's reached from the footer action,
        # not a module card) - same "clear the highlight" treatment
        # Alerts gets.
        self._open_module_page("Support", SupportWindow)
        self._sidebar.set_active(None)

    def _open_change_password(self) -> None:
        from app.ui.change_password_dialog import ChangePasswordDialog

        dialog = ChangePasswordDialog(self._user_service, self._user_data["id"], forced=False, parent=self)
        dialog.exec()

    def _toggle_dark_mode(self, enabled: bool) -> None:
        set_dark_mode(enabled)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app)
        # The avatar is a hand-drawn pixmap (QSS cannot style a
        # QPushButton's icon), so switching theme has to redraw it
        # explicitly - everything else on this button restyles itself
        # automatically via the new stylesheet.
        self._refresh_account_avatar()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt override
        # Refreshes the search index the moment the operator focuses the
        # box, rather than only once at login - a record added mid-shift
        # (a new employee, a newly wired nozzle) should be findable
        # without restarting the app, and this is the cheapest moment to
        # pay for that: right before they start typing, not on every
        # keystroke.
        if obj is self.search_input and event.type() == QEvent.FocusIn:
            self._rebuild_search_index()
        return super().eventFilter(obj, event)

    def _rebuild_search_index(self) -> None:
        """(display label -> handler) for every record this user may see.

        Reuses the exact same services and permission gate
        (_is_card_visible) the sidebar and dashboard already use, so the
        search box can never surface a record its own navigation would
        have hidden from this role.
        """
        actor_id = self._user_data["id"]
        index: dict[str, callable] = {}

        if self._is_card_visible(Permission.EMPLOYEE_VIEW):
            try:
                for employee in self._employee_service.list_employees(actor_id):
                    label = f"{employee.first_name} {employee.last_name}  ·  {employee.employee_code}"
                    index[label] = self._open_employees
            except Exception:  # noqa: BLE001 - search must not break the top bar
                pass

        if self._is_card_visible(Permission.NOZZLE_VIEW):
            try:
                for nozzle in self._nozzle_service.list_nozzles(actor_id):
                    index[f"Nozzle {nozzle.code}"] = self._open_nozzles
            except Exception:  # noqa: BLE001
                pass

        if self._is_card_visible(Permission.INVENTORY_VIEW):
            try:
                for tank in self._tank_service.list_tanks(actor_id):
                    index[f"Tank {tank.code}"] = self._open_tanks
            except Exception:  # noqa: BLE001
                pass

        if self._is_card_visible(Permission.USER_MANAGE):
            try:
                for user in self._user_repo.list_all():
                    index[f"{user.username}  ·  user account"] = self._open_users
            except Exception:  # noqa: BLE001
                pass

        self._search_index = index
        self._search_completer.model().setStringList(sorted(index.keys()))

    def _handle_search_selected(self, label: str) -> None:
        handler = self._search_index.get(label)
        self.search_input.clear()
        if handler is not None:
            handler()

    def _update_clock(self) -> None:
        self.clock_label.setText(datetime.now().strftime("%a, %d %b  ·  %I:%M:%S %p"))

    def _populate_alerts_menu(self) -> None:
        """Rebuilt every time the menu is about to open (not cached) so
        it always reflects the same live data refresh_alert_badge's count
        just did - a stale preview showing different alerts than the
        badge's own number would undermine trust in both.
        """
        from app.ui.notification_window import AlertCard

        self._alerts_menu.clear()
        actor_id = self._user_data["id"]

        container = QWidget()
        container.setObjectName("alertsMenuPanel")
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        try:
            summary = self._notification_service.get_notifications(actor_id)
        except Exception as exc:  # noqa: BLE001
            layout.addWidget(QLabel(describe_unexpected_error(exc)))
            summary = None

        if summary is not None:
            if summary.total == 0:
                all_clear = QLabel("All clear — nothing needs attention right now.")
                all_clear.setObjectName("subtitle")
                layout.addWidget(all_clear)
            else:
                shown = [n for n in summary.notifications if not n.is_summary][:ALERTS_SHOWN_ON_DASHBOARD]
                for notification in shown:
                    layout.addWidget(AlertCard(notification))

                view_all = QPushButton(f"View all {summary.total} alerts →")
                view_all.setObjectName("secondaryButton")
                view_all.setCursor(Qt.PointingHandCursor)
                view_all.clicked.connect(self._go_to_all_alerts)
                layout.addWidget(view_all)

        container.setLayout(layout)
        panel_action = QWidgetAction(self._alerts_menu)
        panel_action.setDefaultWidget(container)
        self._alerts_menu.addAction(panel_action)

    def _go_to_all_alerts(self) -> None:
        self._alerts_menu.close()
        self._open_notifications()

    def _build_account_header(self, user_data: dict, full_name: str):
        """The account menu's top block: avatar, name, role, last login.

        Built once (the name/role/last-login text are fixed for the
        whole session); only the avatar pixmap can change afterwards
        (a theme switch), which _refresh_account_avatar updates in
        place via the returned label reference rather than rebuilding
        this whole widget.
        """
        avatar_label = QLabel()
        avatar_label.setFixedSize(40, 40)

        name_label = QLabel(full_name)
        name_label.setObjectName("accountMenuName")

        role_label = QLabel((user_data.get("role") or "No role").upper())
        role_label.setObjectName("roleTag")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.addWidget(name_label)
        text_layout.addWidget(role_label, alignment=Qt.AlignLeft)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        top_row.addWidget(avatar_label)
        top_row.addLayout(text_layout, stretch=1)

        last_login_label = QLabel("")
        last_login_label.setObjectName("accountMenuLastLogin")
        last_login_label.setWordWrap(True)
        self._set_last_login_text(last_login_label, user_data.get("last_login"))

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(top_row)
        layout.addWidget(last_login_label)

        widget = QWidget()
        widget.setObjectName("accountMenuHeader")
        widget.setAttribute(Qt.WA_StyledBackground, True)
        widget.setLayout(layout)
        return widget, {"avatar": avatar_label, "last_login": last_login_label}

    @staticmethod
    def _set_last_login_text(label: QLabel, last_login_iso: str | None) -> None:
        if not last_login_iso:
            label.setText("First login this session")
            return
        try:
            when = datetime.fromisoformat(last_login_iso)
        except ValueError:
            label.setText("First login this session")
            return
        label.setText("Last login: " + when.strftime("%d %b %Y, %I:%M %p"))

    def _refresh_account_avatar(self) -> None:
        """Redraws the initials pixmap for both the top-bar button and
        the account menu's header - the one piece of this UI that is
        hand-painted rather than QSS-driven, so a theme switch has to
        explicitly repaint it (see _toggle_dark_mode)."""
        initials = self._account_initials()
        icon, pixmap = self._make_avatar(initials)
        self._account_button.setIcon(icon)
        if hasattr(self, "_account_header_labels"):
            self._account_header_labels["avatar"].setPixmap(pixmap)

    def _account_initials(self) -> str:
        first = (self._user_data.get("first_name") or "").strip()
        last = (self._user_data.get("last_name") or "").strip()
        if first or last:
            return f"{first[:1]}{last[:1]}".upper() or self._user_data["username"][:2].upper()
        return self._user_data["username"][:2].upper()

    @staticmethod
    def _make_avatar(initials: str, size: int = 40) -> tuple[QIcon, QPixmap]:
        """A filled-circle initials badge, drawn rather than loaded from
        a file - there is no photo to show for a login account, and this
        is the same "text avatar" convention most desktop and web apps
        use for the same reason.

        Colors are read directly rather than through QSS, since QPainter
        draws pixels once at call time and has no stylesheet to consult -
        matching the light/dark "primary" fill this app's filled buttons
        already use (COLOR_CARBON_BLACK on light, COLOR_PAPER_WHITE on
        dark - see styles.py's module docstring on why that pair
        inverts).
        """
        from app.ui.styles import COLOR_CARBON_BLACK, COLOR_PAPER_WHITE

        dark = is_dark_mode()
        fill = QColor(COLOR_PAPER_WHITE if dark else COLOR_CARBON_BLACK)
        text_color = QColor(COLOR_CARBON_BLACK if dark else COLOR_PAPER_WHITE)

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(0, 0, size, size)
        font = QFont()
        font.setBold(True)
        font.setPointSize(max(10, size // 3))
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, initials)
        painter.end()
        return QIcon(pixmap), pixmap


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
            session_timeout_hours=settings.session_timeout_hours,
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
            ShiftRepository(self._db_session),
            audit_repo,
            self._auth_service,
        )
        self._leave_service = LeaveService(
            LeaveRequestRepository(self._db_session),
            employee_repo,
            audit_repo,
            self._auth_service,
            attendance_service=self._attendance_service,
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
        self._fuel_service = FuelService(
            self._fuel_repo,
            FuelPriceHistoryRepository(self._db_session),
            audit_repo,
            self._auth_service,
        )
        self._tank_repo = TankRepository(self._db_session)
        tank_repo = self._tank_repo
        self._nozzle_service = NozzleService(
            DispenserRepository(self._db_session),
            nozzle_repo,
            self._fuel_repo,
            nozzle_assignment_repo,
            audit_repo,
            self._auth_service,
            tank_repo,
        )
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
            assignment_repo=nozzle_assignment_repo,
        )
        self._backup_service = BackupService(
            db_connection.DB_PATH,
            audit_repo,
            self._auth_service,
        )
        self._audit_service = AuditService(audit_repo, self._auth_service)
        self._settings_service = SettingsService(
            AppSettingRepository(self._db_session), audit_repo, self._auth_service
        )
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
        sale_repo = SaleRepository(self._db_session)
        purchase_order_repo = PurchaseOrderRepository(self._db_session)
        customer_repo = CustomerRepository(self._db_session)
        tender_repo = TenderRepository(self._db_session)
        self._expense_service = ExpenseService(
            ExpenseRepository(self._db_session),
            ExpenseCategoryRepository(self._db_session),
            employee_repo,
            ShiftRepository(self._db_session),
            audit_repo,
            self._auth_service,
            tank_service=self._tank_service,
            tender_repo=tender_repo,
        )
        expense_repo = ExpenseRepository(self._db_session)
        shift_reconciliation_repo = ShiftReconciliationRepository(self._db_session)
        self._reconciliation_service = ReconciliationService(
            shift_reconciliation_repo,
            ShiftRepository(self._db_session),
            sale_repo,
            expense_repo,
            audit_repo,
            self._auth_service,
            tender_repo,
        )
        cash_book_repo = ShiftCashBookRepository(self._db_session)
        employee_shortage_recovery_repo = EmployeeShortageRecoveryRepository(self._db_session)
        self._cash_book_service = ShiftCashBookService(
            cash_book_repo,
            ShiftRepository(self._db_session),
            audit_repo,
            self._auth_service,
            ShiftBankDepositRepository(self._db_session),
            shortage_recovery_repo=employee_shortage_recovery_repo,
        )
        self._employee_shortage_service = EmployeeShortageService(
            EmployeeCashShortageRepository(self._db_session),
            employee_shortage_recovery_repo,
            ShiftReconciliationLineRepository(self._db_session),
            employee_repo,
            ExpenseCategoryRepository(self._db_session),
            self._expense_service,
            audit_repo,
            self._auth_service,
            cash_book_repo,
        )
        credit_account_repo = CreditAccountRepository(self._db_session)
        customer_payment_repo = CustomerPaymentRepository(self._db_session)
        self._credit_service = CreditService(
            credit_account_repo,
            customer_payment_repo,
            customer_repo,
            sale_repo,
            audit_repo,
            self._auth_service,
        )
        payment_repo = PaymentRepository(self._db_session)
        self._sale_service = SaleService(
            sale_repo,
            ShiftRepository(self._db_session),
            nozzle_repo,
            self._fuel_repo,
            employee_repo,
            customer_repo,
            self._tank_repo,
            self._tank_service,
            audit_repo,
            self._auth_service,
            payment_repo,
            self._credit_service,
            tender_repo=tender_repo,
        )
        # SaleService depends on TankService/CreditService, both built
        # after ShiftService above, so it can't be passed in at
        # ShiftService's own construction time - wired in here instead
        # (see ShiftService.attach_sale_service) so completing a nozzle
        # assignment can auto-settle its remaining cash into one Sale.
        self._shift_service.attach_sale_service(self._sale_service)
        self._dashboard_service = DashboardService(
            sale_repo,
            ShiftRepository(self._db_session),
            self._tank_repo,
            purchase_order_repo,
            self._auth_service,
        )
        self._report_service = ReportService(
            self._fuel_repo,
            tank_repo,
            nozzle_repo,
            reconciliation_repo,
            self._auth_service,
            sale_repo,
            payment_repo,
            expense_repo,
            credit_account_repo,
            customer_payment_repo,
            customer_repo,
            shift_reconciliation_repo,
            TankTransactionRepository(self._db_session),
            AttendanceRepository(self._db_session),
            employee_repo,
            ShiftRepository(self._db_session),
        )
        self._analytics_service = AnalyticsService(
            sale_repo,
            expense_repo,
            PurchaseOrderItemRepository(self._db_session),
            self._fuel_repo,
            self._auth_service,
        )
        # Wired last because it reads across nearly every module - it is a
        # consumer of the others, never a dependency of them, which is why
        # nothing above needs to know it exists.
        self._notification_service = NotificationService(
            tank_repo=tank_repo,
            fuel_reconciliation_repo=reconciliation_repo,
            shift_reconciliation_repo=shift_reconciliation_repo,
            expense_repo=expense_repo,
            employee_repo=employee_repo,
            attendance_repo=AttendanceRepository(self._db_session),
            credit_account_repo=credit_account_repo,
            supplier_invoice_repo=SupplierInvoiceRepository(self._db_session),
            supplier_payment_repo=SupplierPaymentRepository(self._db_session),
            audit_repo=audit_repo,
            credit_service=self._credit_service,
            auth_service=self._auth_service,
            db_path=db_connection.DB_PATH,
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
            self._leave_service,
            self._shift_service,
            self._nozzle_service,
            self._tank_service,
            self._report_service,
            self._user_service,
            self._backup_service,
            self._audit_service,
            self._procurement_service,
            self._sale_service,
            self._credit_service,
            self._expense_service,
            self._reconciliation_service,
            self._cash_book_service,
            self._employee_shortage_service,
            self._analytics_service,
            self._dashboard_service,
            self._fuel_service,
            self._settings_service,
            self._notification_service,
            self._role_repo,
            self._fuel_repo,
            self._user_repo,
            self._tank_repo,
            user_data,
        )
        self.main_window.logout_requested.connect(self._on_logout)
        self.main_window.show()

    def _on_logout(self, _expired: bool) -> None:
        if self.main_window:
            self.main_window.close()
            self.main_window = None
        self._show_login()

    def shutdown(self) -> None:
        """Release everything this controller owns.

        The controller holds a long-lived database session and the two
        top-level windows, and until now nothing ever gave them back.
        In the real application that was survivable, because the process
        exits immediately afterwards and the operating system reclaims
        it all. It was NOT survivable anywhere a controller is created
        more than once in a single process - which is exactly what the
        UI test suite does, one per test, and is a direct contributor to
        the cumulative native-resource crash that forces CI to run the
        suite in batches.

        Stopping the session timer first matters: it is what would
        otherwise fire against half-torn-down state.

        Every step is individually guarded because shutdown must always
        complete. Something already being closed, or already gone, is
        the normal case here rather than an error.
        """
        for window in (self.main_window, self.login_window):
            if window is None:
                continue
            with contextlib.suppress(Exception):  # shutdown must never raise
                timer = getattr(window, "_session_timer", None)
                if timer is not None:
                    timer.stop()
                window.close()
                window.deleteLater()
        self.main_window = None
        self.login_window = None

        with contextlib.suppress(Exception):
            self._db_session.close()


def launch_app() -> None:
    app = QApplication([])
    apply_theme(app)
    controller = AppController()
    controller.start()
    try:
        app.exec()
    finally:
        # Closes the database session rather than relying on process
        # exit to do it. WAL mode leaves -wal/-shm sidecar files that a
        # clean close checkpoints back into the database file.
        controller.shutdown()
