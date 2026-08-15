from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import Permission
from app.core.exceptions import SessionExpiredError
from app.database import connection as db_connection
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_document_repository import EmployeeDocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService
from app.services.employee_service import EmployeeService
from app.ui.styles import STYLESHEET

SESSION_CHECK_INTERVAL_MS = 60_000


class MainWindow(QMainWindow):
    """Landing screen after login. Shows the current user and lets them log out."""

    logout_requested = Signal(bool)  # bool: True if the logout was due to session expiry

    def __init__(self, auth_service: AuthService, employee_service: EmployeeService, user_data: dict):
        super().__init__()
        self._auth_service = auth_service
        self._employee_service = employee_service
        self._user_data = user_data
        self._session_token = user_data["session_token"]
        self._employee_window = None

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

        logout_button = QPushButton("Logout")
        logout_button.setObjectName("secondaryButton")
        logout_button.setCursor(Qt.PointingHandCursor)
        logout_button.clicked.connect(self._logout)

        top_bar_layout.addWidget(user_label)
        top_bar_layout.addSpacing(8)
        top_bar_layout.addWidget(role_tag)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(employees_button)
        top_bar_layout.addWidget(logout_button)
        top_bar.setLayout(top_bar_layout)

        message = QLabel("Welcome to Petrol Pump ERP\nMore modules are on the way.")
        message.setObjectName("subtitle")
        message.setAlignment(Qt.AlignCenter)

        body = QWidget()
        body.setObjectName("background")
        body_layout = QVBoxLayout()
        body_layout.addStretch()
        body_layout.addWidget(message)
        body_layout.addStretch()
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

    def _logout(self) -> None:
        self._session_timer.stop()
        self._auth_service.logout(self._session_token)
        self.logout_requested.emit(False)

    def _open_employees(self) -> None:
        from app.ui.employee_window import EmployeeListWindow

        self._employee_window = EmployeeListWindow(self._employee_service, self._auth_service, self._user_data["id"])
        self._employee_window.show()


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
        self._employee_service = EmployeeService(
            EmployeeRepository(self._db_session),
            EmployeeDocumentRepository(self._db_session),
            user_repo,
            RoleRepository(self._db_session),
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

        self.main_window = MainWindow(self._auth_service, self._employee_service, user_data)
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
