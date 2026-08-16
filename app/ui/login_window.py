"""Login screen. Pure presentation — all authentication logic lives in AuthService."""

import platform

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from app.services.auth_service import AuthService
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error

HERO_BULLETS = [
    "Works fully offline",
    "Role-based access control",
    "Complete audit trail",
]


def get_device_info() -> str:
    return platform.node() or "unknown-device"


def _build_hero_panel() -> QWidget:
    """Left-hand brand panel: what makes the login screen feel like a
    product rather than a bare form."""
    panel = QWidget()
    panel.setObjectName("heroPanel")
    panel.setMinimumWidth(380)

    badge = QWidget()
    badge.setObjectName("heroBadge")
    badge.setFixedSize(44, 44)
    badge_layout = QVBoxLayout(badge)
    badge_layout.setContentsMargins(0, 0, 0, 0)
    badge_glyph = QLabel("⛽")
    badge_glyph.setObjectName("heroBadgeGlyph")
    badge_glyph.setAlignment(Qt.AlignCenter)
    badge_layout.addWidget(badge_glyph)

    title = QLabel("Petrol Pump ERP")
    title.setObjectName("heroTitle")
    title.setWordWrap(True)

    tagline = QLabel("Sales, shifts, staff, and attendance — built to run reliably without the internet.")
    tagline.setObjectName("heroTagline")
    tagline.setWordWrap(True)

    bullets_layout = QVBoxLayout()
    bullets_layout.setSpacing(10)
    for text in HERO_BULLETS:
        bullet = QLabel(f"✓  {text}")
        bullet.setObjectName("heroBullet")
        bullets_layout.addWidget(bullet)

    content_layout = QVBoxLayout()
    content_layout.setContentsMargins(48, 56, 48, 56)
    content_layout.setSpacing(0)
    content_layout.addWidget(badge)
    content_layout.addSpacing(28)
    content_layout.addWidget(title)
    content_layout.addSpacing(12)
    content_layout.addWidget(tagline)
    content_layout.addSpacing(32)
    content_layout.addLayout(bullets_layout)
    content_layout.addStretch()

    panel.setLayout(content_layout)
    return panel


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
        self.setMinimumSize(820, 500)

        form_side = QWidget()
        form_side.setObjectName("background")

        card = QWidget()
        card.setObjectName("card")
        card.setFixedWidth(340)
        card_shadow = QGraphicsDropShadowEffect(card)
        card_shadow.setBlurRadius(28)
        card_shadow.setOffset(0, 8)
        card_shadow.setColor(QColor(79, 70, 229, 35))
        card.setGraphicsEffect(card_shadow)

        heading = QLabel("Welcome back")
        heading.setObjectName("title")
        heading.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Sign in to continue")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self._attempt_login)

        chain_enter_to_next_field(self.username_input, self.password_input)

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
        card_layout.addWidget(heading)
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

        form_layout = QVBoxLayout()
        form_layout.addStretch()
        form_layout.addWidget(card, alignment=Qt.AlignCenter)
        form_layout.addStretch()
        form_side.setLayout(form_layout)

        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(_build_hero_panel(), stretch=4)
        root_layout.addWidget(form_side, stretch=5)

        root = QWidget()
        root.setLayout(root_layout)
        self.setCentralWidget(root)

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
