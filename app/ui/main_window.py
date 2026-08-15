from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
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
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.nozzle_assignment_repository import NozzleAssignmentRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.attendance_service import AttendanceService
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.services.shift_service import ShiftService
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
        user_data: dict,
    ):
        super().__init__()
        self._auth_service = auth_service
        self._employee_service = employee_service
        self._attendance_service = attendance_service
        self._shift_service = shift_service
        self._user_data = user_data
        self._session_token = user_data["session_token"]
        self._employee_window = None
        self._attendance_window = None
        self._shift_window = None

        self.setWindowTitle("Petrol Pump ERP")
        self.setMinimumSize(720, 520)

        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(20, 14, 20, 14)

        user_label = QLabel(user_data["username"])
        user_label.setObjectName("userLabel")

        role_tag = QLabel(user_data.get("role") or "No role")
        role_tag.setObjectName("roleTag")

        employees_button = QPushButton("Employees")
        employees_button.setObjectName("secondaryButton")
        employees_button.setCursor(Qt.PointingHandCursor)
        employees_button.clicked.connect(self._open_employees)
        employees_button.setVisible(
            self._auth_service.check_permission(user_data["id"], Permission.EMPLOYEE_VIEW.value)
        )

        attendance_button = QPushButton("Attendance")
        attendance_button.setObjectName("secondaryButton")
        attendance_button.setCursor(Qt.PointingHandCursor)
        attendance_button.clicked.connect(self._open_attendance)
        attendance_button.setVisible(
            self._auth_service.check_permission(user_data["id"], Permission.ATTENDANCE_VIEW.value)
        )

        shifts_button = QPushButton("Shifts")
        shifts_button.setObjectName("secondaryButton")
        shifts_button.setCursor(Qt.PointingHandCursor)
        shifts_button.clicked.connect(self._open_shifts)
        shifts_button.setVisible(self._auth_service.check_permission(user_data["id"], Permission.SHIFT_VIEW.value))

        logout_button = QPushButton("Logout")
        logout_button.setObjectName("secondaryButton")
        logout_button.setCursor(Qt.PointingHandCursor)
        logout_button.clicked.connect(self._logout)

        top_bar_layout.addWidget(user_label)
        top_bar_layout.addSpacing(8)
        top_bar_layout.addWidget(role_tag)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(employees_button)
        top_bar_layout.addWidget(attendance_button)
        top_bar_layout.addWidget(shifts_button)
        top_bar_layout.addWidget(logout_button)
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

        cards = [
            ("👥", "Employees", "Staff, documents, and status", self._open_employees, Permission.EMPLOYEE_VIEW),
            ("🕒", "Attendance", "Mark and review attendance", self._open_attendance, Permission.ATTENDANCE_VIEW),
            ("⛽", "Shifts", "Open/close shifts, assign nozzles", self._open_shifts, Permission.SHIFT_VIEW),
        ]

        cards_grid = QGridLayout()
        cards_grid.setSpacing(16)
        column = 0
        for icon, title, subtitle, handler, permission in cards:
            if not self._auth_service.check_permission(user_data["id"], permission.value):
                continue
            cards_grid.addWidget(DashboardCard(icon, title, subtitle, handler), 0, column)
            cards_grid.setColumnStretch(column, 1)
            column += 1

        empty_state = QLabel("Nothing to show yet — ask an administrator for access to a module.")
        empty_state.setObjectName("subtitle")

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(32, 32, 32, 32)
        body_layout.setSpacing(24)
        body_layout.addLayout(header_layout)
        if column > 0:
            body_layout.addLayout(cards_grid)
        else:
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


class AppController:
    """Owns the login <-> main window transition and the shared AuthService."""

    def __init__(self):
        self._db_session = db_connection.SessionLocal()
        user_repo = UserRepository(self._db_session)
        audit_repo = AuditLogRepository(self._db_session)
        self._auth_service = AuthService(
            user_repo,
            audit_repo,
            UserSessionRepository(self._db_session),
        )
        employee_repo = EmployeeRepository(self._db_session)
        self._employee_service = EmployeeService(
            employee_repo,
            EmployeeDocumentRepository(self._db_session),
            user_repo,
            RoleRepository(self._db_session),
            audit_repo,
            self._auth_service,
        )
        self._attendance_service = AttendanceService(
            AttendanceRepository(self._db_session),
            employee_repo,
            audit_repo,
            self._auth_service,
        )
        self._shift_service = ShiftService(
            ShiftRepository(self._db_session),
            NozzleAssignmentRepository(self._db_session),
            employee_repo,
            NozzleRepository(self._db_session),
            user_repo,
            audit_repo,
            self._auth_service,
        )
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

        self.main_window = MainWindow(
            self._auth_service, self._employee_service, self._attendance_service, self._shift_service, user_data
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
