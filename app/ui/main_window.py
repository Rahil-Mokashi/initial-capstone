import contextlib
import platform
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.config import settings
from app.core.constants import Permission
from app.core.exceptions import SessionExpiredError
from app.database import connection as db_connection
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.app_setting_repository import AppSettingRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.dispenser_repository import DispenserRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.expense_repository import ExpenseCategoryRepository, ExpenseRepository
from app.repositories.fuel_delivery_repository import FuelDeliveryRepository
from app.repositories.fuel_price_history_repository import FuelPriceHistoryRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.purchase_order_repository import PurchaseOrderItemRepository, PurchaseOrderRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
from app.repositories.supplier_invoice_repository import SupplierInvoiceRepository, SupplierPaymentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.tank_reading_repository import TankReadingRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
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
from app.services.settings_service import SettingsService
from app.services.notification_service import NotificationService
from app.services.nozzle_service import NozzleService
from app.services.procurement_service import ProcurementService
from app.services.reconciliation_service import ReconciliationService
from app.services.report_service import ReportService
from app.services.sale_service import SaleService
from app.services.shift_service import ShiftService
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.tank_service import TankService
from app.services.user_service import UserService
from app.ui.background import is_widget_alive
from app.ui.qt_utils import apply_hard_shadow, describe_unexpected_error
from app.ui.sidebar import SIDEBAR_WIDTH, Sidebar
from app.ui.theme import apply_theme, is_dark_mode, set_dark_mode
from app.ui.widgets import GridBackgroundWidget

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
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        layout.addWidget(icon_label)
        layout.addLayout(text_layout, stretch=1)
        self.setLayout(layout)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(108)

        apply_hard_shadow(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


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

        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(DASHBOARD_PAGE_MARGIN, 14, DASHBOARD_PAGE_MARGIN, 14)

        user_label = QLabel(user_data["username"])
        user_label.setObjectName("userLabel")

        role_tag = QLabel((user_data.get("role") or "No role").upper())
        role_tag.setObjectName("roleTag")

        account_button = QPushButton("Account")
        account_button.setObjectName("secondaryButton")
        account_button.setCursor(Qt.PointingHandCursor)
        account_menu = QMenu(account_button)
        account_menu.addAction("Change Password", self._open_change_password)
        account_menu.addSeparator()
        self._dark_mode_action = account_menu.addAction("Dark Mode")
        self._dark_mode_action.setCheckable(True)
        self._dark_mode_action.setChecked(is_dark_mode())
        self._dark_mode_action.toggled.connect(self._toggle_dark_mode)
        account_menu.addSeparator()
        account_menu.addAction("Logout", self._logout)
        account_button.setMenu(account_menu)

        # The alert count belongs in the top bar rather than on a dashboard
        # card, because it must be visible from every state of this screen
        # - including when the operator has scrolled the cards out of view.
        # It carries the count itself so an unattended critical problem is
        # apparent without opening anything.
        self.alerts_button = QPushButton("Alerts")
        self.alerts_button.setObjectName("alertsButton")
        self.alerts_button.setCursor(Qt.PointingHandCursor)
        self.alerts_button.clicked.connect(self._open_notifications)

        top_bar_layout.addWidget(user_label)
        top_bar_layout.addSpacing(8)
        top_bar_layout.addWidget(role_tag)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.alerts_button)
        top_bar_layout.addSpacing(8)
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

        self._card_groups = [
            (
                "DAILY OPERATIONS",
                [
                    ("👥", "Employees", "Staff, documents, and status", self._open_employees, Permission.EMPLOYEE_VIEW),
                    ("🕒", "Attendance", "Mark and review attendance", self._open_attendance, Permission.ATTENDANCE_VIEW),
                    ("⛽", "Shifts", "Open/close shifts, assign nozzles", self._open_shifts, Permission.SHIFT_VIEW),
                    ("🪪", "My Shift", "Your current nozzle and fuel assignment", self._open_my_shift, Permission.MY_ASSIGNMENT_VIEW),
                    ("⚡", "Terminal", "Fast fuel-sale entry at the pump", self._open_terminal, Permission.SALE_MANAGE),
                    ("💳", "Sales", "Record sales and manage customers", self._open_sales, Permission.SALE_VIEW),
                    ("🧾", "Credit", "Credit accounts, payments, and balances", self._open_credit, Permission.CREDIT_VIEW),
                    ("🧮", "Expenses", "Record and approve pump expenses", self._open_expenses, Permission.EXPENSE_VIEW),
                    ("⚖️", "Reconciliation", "Reconcile cash, UPI, and card per shift", self._open_reconciliation, Permission.RECONCILIATION_VIEW),
                    ("🔧", "Nozzles", "Manage dispensers and nozzles", self._open_nozzles, Permission.NOZZLE_VIEW),
                    ("🛢️", "Tanks", "Stock, transactions, reconciliation", self._open_tanks, Permission.INVENTORY_VIEW),
                    ("🏷️", "Fuel Prices", "Set selling rates, view price history", self._open_fuel_prices, Permission.FUEL_PRICE_VIEW),
                    ("🚛", "Procurement", "Suppliers, orders, and deliveries", self._open_procurement, Permission.PROCUREMENT_VIEW),
                ],
            ),
            (
                "REPORTS & ADMINISTRATION",
                [
                    (
                        "📊", "Reports", "Sales, payments, credit, expenses, and inventory",
                        self._open_reports,
                        (Permission.INVENTORY_VIEW, Permission.SALE_VIEW, Permission.EXPENSE_VIEW, Permission.CREDIT_VIEW, Permission.RECONCILIATION_VIEW, Permission.ANALYTICS_VIEW),
                    ),
                    ("🔐", "Users", "Create logins and manage roles", self._open_users, Permission.USER_MANAGE),
                    ("⚙️", "Settings", "Company profile, printing, backups", self._open_settings, Permission.SETTINGS_VIEW),
                    ("🗄️", "Backups", "Back up or restore the database", self._open_backups, Permission.BACKUP_MANAGE),
                    ("📜", "Audit Log", "Review every recorded change", self._open_audit_log, Permission.AUDIT_VIEW),
                ],
            ),
        ]
        self._stat_tiles = self._build_stat_tiles(user_data["id"])
        self._dashboard_columns = 0  # forces the first _populate_dashboard call to actually build

        self._dynamic_dashboard_layout = QVBoxLayout()
        self._dynamic_dashboard_layout.setSpacing(28)

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(DASHBOARD_PAGE_MARGIN, DASHBOARD_PAGE_MARGIN, DASHBOARD_PAGE_MARGIN, DASHBOARD_PAGE_MARGIN)
        body_layout.setSpacing(28)
        body_layout.addLayout(header_layout)

        # Built once here (not inside _populate_dashboard, which clears and
        # rebuilds its own layout on every column-count change during a
        # resize) so resizing the window never re-fetches or re-renders
        # the chart's data - same reasoning _stat_tiles is computed once
        # in __init__ rather than inside _populate_dashboard.
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

        body_layout.addLayout(self._dynamic_dashboard_layout)
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

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(top_bar)
        content_layout.addWidget(self._breadcrumb_bar)
        content_layout.addWidget(self._content_stack, stretch=1)

        content_column = QWidget()
        content_column.setLayout(content_layout)

        self._sidebar = Sidebar(
            app_name="Petrol Pump ERP",
            device_label=platform.node() or "unknown-device",
            groups=self._card_groups,
            is_card_visible=self._is_card_visible,
            home_action=("🏠", "Dashboard", self._go_home),
            footer_actions=[
                ("🆘", "Support", self._open_support),
                ("🔑", "Change Password", self._open_change_password),
                ("🚪", "Logout", self._logout),
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

    def _populate_dashboard(self, columns: int) -> None:
        self._dashboard_columns = columns
        self._clear_layout(self._dynamic_dashboard_layout)

        if self._stat_tiles:
            stat_columns = min(len(self._stat_tiles), max(columns, 1))
            stats_grid = QGridLayout()
            stats_grid.setSpacing(16)
            for column in range(stat_columns):
                stats_grid.setColumnStretch(column, 1)
            for index, (value, label, tone) in enumerate(self._stat_tiles):
                row, column = divmod(index, stat_columns)
                stats_grid.addWidget(StatCard(value, label, tone), row, column)
            self._dynamic_dashboard_layout.addLayout(stats_grid)

        total_visible_cards = 0
        for group_label, cards in self._card_groups:
            visible_cards = [
                (icon, title, subtitle, handler)
                for icon, title, subtitle, handler, permission in cards
                if self._is_card_visible(permission)
            ]
            if not visible_cards:
                continue
            total_visible_cards += len(visible_cards)

            group_label_widget = QLabel(group_label)
            group_label_widget.setObjectName("dashGroupLabel")

            group_grid = QGridLayout()
            group_grid.setSpacing(16)
            for column in range(columns):
                group_grid.setColumnStretch(column, 1)
            for index, (icon, title, subtitle, handler) in enumerate(visible_cards):
                row, column = divmod(index, columns)
                group_grid.addWidget(DashboardCard(icon, title, subtitle, handler), row, column)

            group_layout = QVBoxLayout()
            group_layout.setSpacing(10)
            group_layout.addWidget(group_label_widget)
            group_layout.addLayout(group_grid)
            self._dynamic_dashboard_layout.addLayout(group_layout)

        if total_visible_cards == 0:
            empty_state = QLabel("Nothing to show yet — ask an administrator for access to a module.")
            empty_state.setObjectName("subtitle")
            self._dynamic_dashboard_layout.addWidget(empty_state)

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
            return

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

    def _go_back(self) -> None:
        if not self._page_stack:
            return
        widget, _title, _key = self._page_stack.pop()
        self._content_stack.removeWidget(widget)
        widget.deleteLater()
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
            self._content_stack.removeWidget(widget)
            widget.deleteLater()
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
            self._content_stack.removeWidget(widget)
            widget.deleteLater()
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

    def _open_employees(self) -> None:
        from app.ui.employee_window import EmployeeListWindow

        self._open_module_page(
            "Employees",
            lambda: EmployeeListWindow(self._employee_service, self._auth_service, self._user_data["id"]),
        )

    def _open_attendance(self) -> None:
        from app.ui.attendance_window import AttendanceWindow

        self._open_module_page(
            "Attendance",
            lambda: AttendanceWindow(
                self._attendance_service, self._employee_service, self._auth_service, self._user_data["id"]
            ),
        )

    def _open_shifts(self) -> None:
        from app.ui.shift_window import ShiftListWindow

        self._open_module_page(
            "Shifts",
            lambda: ShiftListWindow(
                self._shift_service, self._employee_service, self._auth_service, self._user_data["id"]
            ),
        )

    def _open_nozzles(self) -> None:
        from app.ui.nozzle_window import NozzleManagementWindow

        self._open_module_page(
            "Nozzles",
            lambda: NozzleManagementWindow(
                self._nozzle_service, self._fuel_repo, self._tank_repo, self._auth_service, self._user_data["id"]
            ),
        )

    def _open_settings(self) -> None:
        from app.ui.settings_window import SettingsWindow

        self._open_module_page(
            "Settings",
            lambda: SettingsWindow(self._settings_service, self._user_data["id"], self._auth_service),
        )

    def _open_fuel_prices(self) -> None:
        from app.ui.fuel_price_window import FuelPriceWindow

        self._open_module_page(
            "Fuel Prices",
            lambda: FuelPriceWindow(self._user_data["id"], self._fuel_service, self._auth_service),
        )

    def _open_tanks(self) -> None:
        from app.ui.tank_window import TankListWindow

        self._open_module_page(
            "Tanks",
            lambda: TankListWindow(
                self._tank_service, self._employee_service, self._fuel_repo, self._auth_service, self._user_data["id"]
            ),
        )

    def _open_procurement(self) -> None:
        from app.ui.procurement_window import ProcurementWindow

        self._open_module_page(
            "Procurement",
            lambda: ProcurementWindow(
                self._procurement_service,
                self._fuel_repo,
                self._tank_service,
                self._employee_service,
                self._auth_service,
                self._user_data["id"],
            ),
        )

    def _open_terminal(self) -> None:
        from app.ui.terminal_window import TerminalWindow

        self._open_module_page(
            "Terminal",
            lambda: TerminalWindow(
                self._sale_service,
                self._shift_service,
                self._employee_service,
                self._auth_service,
                self._user_data["id"],
            ),
        )

    def _open_sales(self) -> None:
        from app.ui.sales_window import SalesWindow

        self._open_module_page(
            "Sales",
            lambda: SalesWindow(
                self._sale_service,
                self._shift_service,
                self._employee_service,
                self._auth_service,
                self._user_data["id"],
                self._report_service,
            ),
        )

    def _open_credit(self) -> None:
        from app.ui.credit_window import CreditWindow

        self._open_module_page(
            "Credit",
            lambda: CreditWindow(self._credit_service, self._sale_service, self._auth_service, self._user_data["id"]),
        )

    def _open_expenses(self) -> None:
        from app.ui.expense_window import ExpenseWindow

        self._open_module_page(
            "Expenses",
            lambda: ExpenseWindow(
                self._expense_service, self._employee_service, self._shift_service, self._auth_service, self._user_data["id"]
            ),
        )

    def _open_reconciliation(self) -> None:
        from app.ui.reconciliation_window import ReconciliationWindow

        self._open_module_page(
            "Reconciliation",
            lambda: ReconciliationWindow(
                self._reconciliation_service, self._shift_service, self._auth_service, self._user_data["id"]
            ),
        )

    def _open_my_shift(self) -> None:
        from app.ui.my_shift_window import MyShiftWindow

        self._open_module_page(
            "My Shift",
            lambda: MyShiftWindow(self._shift_service, self._auth_service, self._user_data["id"]),
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
        self._expense_service = ExpenseService(
            ExpenseRepository(self._db_session),
            ExpenseCategoryRepository(self._db_session),
            employee_repo,
            ShiftRepository(self._db_session),
            audit_repo,
            self._auth_service,
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
        )
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
