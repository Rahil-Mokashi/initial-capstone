"""Login screen. Pure presentation — all authentication logic lives in AuthService."""

import platform

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from app.services.auth_service import AuthService
from app.ui.qt_utils import describe_unexpected_error


def get_device_info() -> str:
    return platform.node() or "unknown-device"


class LoginWindow(QMainWindow):
    """Collects credentials and delegates authentication to AuthService.

    Emits login_succeeded(dict) with the AuthService user_data payload
    (including a session_token) on success. Never touches the database or
    password logic directly.
    """

    login_succeeded = Signal(dict)

    def __init__(self, auth_service: AuthService):
        super().__init__()
        self._auth_service = auth_service

        self.setWindowTitle("Petrol Pump ERP - Login")
        self.setMinimumSize(420, 480)

        background = QWidget()
        background.setObjectName("background")

        card = QWidget()
        card.setObjectName("card")
        card.setFixedWidth(340)
        card_shadow = QGraphicsDropShadowEffect(card)
        card_shadow.setBlurRadius(24)
        card_shadow.setOffset(0, 6)
        card_shadow.setColor(QColor(0, 0, 0, 40))
        card.setGraphicsEffect(card_shadow)

        title = QLabel("Petrol Pump ERP")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Sign in to continue")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self._attempt_login)

        self.login_button = QPushButton("Login")
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.clicked.connect(self._attempt_login)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(32, 36, 32, 36)
        card_layout.setSpacing(6)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(24)
        card_layout.addWidget(self.username_input)
        card_layout.addSpacing(10)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(20)
        card_layout.addWidget(self.login_button)
        card_layout.addSpacing(12)
        card_layout.addWidget(self.error_label)
        card.setLayout(card_layout)

        background_layout = QVBoxLayout()
        background_layout.addStretch()
        background_layout.addWidget(card, alignment=Qt.AlignCenter)
        background_layout.addStretch()
        background.setLayout(background_layout)

        self.setCentralWidget(background)
        self.username_input.setFocus()

    def _attempt_login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        self._set_error("")

        if not username or not password:
            self._set_error("Enter both username and password.")
            return

        try:
            success, user_data, error = self._auth_service.authenticate(
                username, password, device_info=get_device_info()
            )
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the login screen
            self._set_error(describe_unexpected_error(exc))
            return

        if not success:
            self._set_error(error or "Login failed.")
            self.password_input.clear()
            self.password_input.setFocus()
            return

        self.password_input.clear()
        self.login_succeeded.emit(user_data)

    def _set_error(self, text: str) -> None:
        self.error_label.setText(text)
        self.error_label.setVisible(bool(text))
