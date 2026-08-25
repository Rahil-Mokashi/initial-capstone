"""Login screen. Pure presentation — all authentication logic lives in AuthService.

Redesigned 2026-08-25 alongside the PetrolStream reskin: the previous
version left the hero panel's lower half empty (title + 3 bullets, then
nothing) and the form card was placeholder-only inputs with no field
labels - a known usability anti-pattern, since a placeholder disappears
the moment someone starts typing and the field loses its identity. This
pass fills the hero panel with real content (feature rows built from the
same icon-chip language the dashboard already uses, and a footer that
shows the two things actually useful to know at a glance on a shared
terminal - which device this is, and today's date) and gives the form
real field labels, a password visibility toggle, and a security pill
that makes the card read as a deliberate product surface rather than a
bare form.
"""

import platform
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.auth_service import AuthService
from app.ui.qt_utils import apply_hard_shadow, chain_enter_to_next_field, describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget

# (icon, title, description) - the same icon-chip + title + description
# shape DashboardCard already uses, restated for the dark hero panel.
HERO_FEATURES = [
    ("📡", "Fully offline", "No internet or cloud dependency, ever."),
    ("🔐", "Role-based access", "Six roles, permission-checked on every action."),
    ("📜", "Complete audit trail", "Every change is logged and reviewable."),
]


def get_device_info() -> str:
    return platform.node() or "unknown-device"


def _build_hero_feature_row(icon: str, title: str, description: str) -> QWidget:
    icon_box = QWidget()
    icon_box.setObjectName("heroFeatureIcon")
    icon_box.setFixedSize(34, 34)
    icon_layout = QVBoxLayout(icon_box)
    icon_layout.setContentsMargins(0, 0, 0, 0)
    icon_glyph = QLabel(icon)
    icon_glyph.setObjectName("heroFeatureIconGlyph")
    icon_layout.addWidget(icon_glyph)

    title_label = QLabel(title)
    title_label.setObjectName("heroFeatureTitle")

    desc_label = QLabel(description)
    desc_label.setObjectName("heroFeatureDesc")
    desc_label.setWordWrap(True)

    text_column = QVBoxLayout()
    text_column.setContentsMargins(0, 0, 0, 0)
    text_column.setSpacing(1)
    text_column.addWidget(title_label)
    text_column.addWidget(desc_label)

    row = QHBoxLayout()
    row.setSpacing(14)
    row.addWidget(icon_box)
    row.addLayout(text_column, stretch=1)

    wrapper = QWidget()
    wrapper.setLayout(row)
    return wrapper


def _build_hero_panel() -> QWidget:
    """Left-hand brand panel: what makes the login screen feel like a
    product rather than a bare form."""
    panel = GridBackgroundWidget(force_dark_dots=True)
    panel.setObjectName("heroPanel")
    panel.setMinimumWidth(420)

    badge = QWidget()
    badge.setObjectName("heroBadge")
    badge.setFixedSize(48, 48)
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

    features_layout = QVBoxLayout()
    features_layout.setSpacing(20)
    for icon, feature_title, description in HERO_FEATURES:
        features_layout.addWidget(_build_hero_feature_row(icon, feature_title, description))

    top_content = QVBoxLayout()
    top_content.setContentsMargins(0, 0, 0, 0)
    top_content.setSpacing(0)
    top_content.addWidget(badge)
    top_content.addSpacing(28)
    top_content.addWidget(title)
    top_content.addSpacing(12)
    top_content.addWidget(tagline)
    top_content.addSpacing(36)
    top_content.addLayout(features_layout)

    # A bottom-anchored footer so the panel's lower half carries real,
    # genuinely useful information (which shared terminal this is, what
    # today's date is) instead of sitting empty - deliberately not a
    # fabricated "v1.0"-style version tag, since nothing in this codebase
    # tracks a real version number to show truthfully.
    device_label = QLabel(f"DEVICE — {get_device_info().upper()}")
    device_label.setObjectName("heroFooterText")

    date_label = QLabel(datetime.now().strftime("%A, %d %B %Y").upper())
    date_label.setObjectName("heroFooterText")

    footer_layout = QHBoxLayout()
    footer_layout.setContentsMargins(0, 16, 0, 0)
    footer_layout.addWidget(device_label)
    footer_layout.addStretch()
    footer_layout.addWidget(date_label)

    footer = QWidget()
    footer.setObjectName("heroFooter")
    footer.setLayout(footer_layout)

    content_layout = QVBoxLayout()
    content_layout.setContentsMargins(48, 56, 48, 32)
    content_layout.setSpacing(0)
    content_layout.addLayout(top_content)
    content_layout.addStretch()
    content_layout.addWidget(footer)

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
        self.setMinimumSize(900, 560)

        form_side = GridBackgroundWidget()
        form_side.setObjectName("background")

        card = QWidget()
        card.setObjectName("card")
        card.setFixedWidth(380)
        apply_hard_shadow(card)

        security_pill = QLabel("STAFF SIGN-IN")
        security_pill.setObjectName("roleTag")
        security_pill.setAlignment(Qt.AlignCenter)
        # A pill can't center itself inside a stretching layout without
        # being wrapped - this row just holds it centered above the heading.
        pill_row = QHBoxLayout()
        pill_row.addStretch()
        pill_row.addWidget(security_pill)
        pill_row.addStretch()

        heading = QLabel("Welcome back")
        heading.setObjectName("title")
        heading.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Sign in with your pump account to continue")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)

        username_label = QLabel("USERNAME")
        username_label.setObjectName("fieldLabel")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("e.g. attendant1")

        password_label = QLabel("PASSWORD")
        password_label.setObjectName("fieldLabel")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Your password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self._attempt_login)

        self.toggle_password_button = QPushButton("Show")
        self.toggle_password_button.setObjectName("togglePasswordButton")
        self.toggle_password_button.setCursor(Qt.PointingHandCursor)
        self.toggle_password_button.setFixedHeight(self.password_input.sizeHint().height())
        self.toggle_password_button.clicked.connect(self._toggle_password_visibility)

        password_row = QHBoxLayout()
        password_row.setSpacing(8)
        password_row.addWidget(self.password_input, stretch=1)
        password_row.addWidget(self.toggle_password_button)

        chain_enter_to_next_field(self.username_input, self.password_input)

        self.login_button = QPushButton("Login →")
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.setMinimumHeight(44)
        self.login_button.clicked.connect(self._attempt_login)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        footnote = QLabel("Locked out or need a reset? Ask an administrator to sort you out on the Users screen.")
        footnote.setObjectName("loginFootnote")
        footnote.setAlignment(Qt.AlignCenter)
        footnote.setWordWrap(True)

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(36, 32, 36, 32)
        card_layout.setSpacing(6)
        card_layout.addLayout(pill_row)
        card_layout.addSpacing(16)
        card_layout.addWidget(heading)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(28)
        card_layout.addWidget(username_label)
        card_layout.addSpacing(4)
        card_layout.addWidget(self.username_input)
        card_layout.addSpacing(16)
        card_layout.addWidget(password_label)
        card_layout.addSpacing(4)
        card_layout.addLayout(password_row)
        card_layout.addSpacing(24)
        card_layout.addWidget(self.login_button)
        card_layout.addSpacing(12)
        card_layout.addWidget(self.error_label)
        card_layout.addSpacing(20)
        card_layout.addWidget(footnote)
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

    def _toggle_password_visibility(self) -> None:
        is_hidden = self.password_input.echoMode() == QLineEdit.Password
        self.password_input.setEchoMode(QLineEdit.Normal if is_hidden else QLineEdit.Password)
        self.toggle_password_button.setText("Hide" if is_hidden else "Show")

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
