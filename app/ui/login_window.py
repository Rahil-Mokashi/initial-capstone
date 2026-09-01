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

Rebranded 2026-08-26: the screen used to read as an internal back-office
tool - "Petrol Pump ERP" spelled out, a literal gas-pump emoji as the
logo mark, "STAFF SIGN-IN", "pump account", and a footnote pointing
someone at the "Users screen." None of that belongs on a login page for
software meant to be deployed commercially to a customer's business -
the product needs a real name and a wordmark, and the copy needs to
read like any other professional product's sign-in page rather than
exposing internal navigation labels. The rest of the application (main
window title, PDF letterhead, installer, docs) still says "Petrol Pump
ERP" - that is a separate, much larger rebrand this pass deliberately
does not touch; scoping it to the login screen keeps the blast radius
to the one surface that was actually asked about.

Re-laid-out later the same day: the split dark-hero-panel/form-on-the-right
layout is gone. The credentials card is now centered on the page, the
brand mark (badge + "FuelDesk") sits above it instead of inside a side
panel, and the same feature/terminal content that used to fill that
panel is now four standalone bold callout cards flanking the centered
card - two on each side - so the page still carries real information,
just distributed around the card instead of stacked beside it.
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

# The login screen's own product identity - see the module docstring for
# why this differs from the "Petrol Pump ERP" name used everywhere else
# in the app (main window title, PDF letterhead, installer, docs).
PRODUCT_NAME = "FuelDesk"
PRODUCT_MARK = "F"

# (icon, title, description) - the same icon-chip + title + description
# shape the dashboard's own cards use, restated as standalone bold cards
# flanking the centered login card instead of rows inside a side panel.
BOLD_FEATURES = [
    ("📡", "Works fully offline", "No internet or cloud dependency, ever."),
    ("🔐", "Role-based access control", "Granular permissions, checked on every action."),
    ("📜", "Complete audit trail", "Every change is logged and reviewable."),
]

BOLD_CARD_WIDTH = 200


def get_device_info() -> str:
    return platform.node() or "unknown-device"


def _build_brand_header() -> QWidget:
    """Badge + product name, centered above the login card."""
    badge = QWidget()
    badge.setObjectName("heroBadge")
    badge.setFixedSize(56, 56)
    badge_layout = QVBoxLayout(badge)
    badge_layout.setContentsMargins(0, 0, 0, 0)
    badge_glyph = QLabel(PRODUCT_MARK)
    badge_glyph.setObjectName("heroBadgeGlyph")
    badge_glyph.setAlignment(Qt.AlignCenter)
    badge_layout.addWidget(badge_glyph)

    title = QLabel(PRODUCT_NAME)
    title.setObjectName("brandTitle")

    mark_row = QHBoxLayout()
    mark_row.setSpacing(16)
    mark_row.addWidget(badge)
    mark_row.addWidget(title)
    mark_row_wrap = QWidget()
    mark_row_wrap.setLayout(mark_row)

    tagline = QLabel("Secure sign-in to your operations platform")
    tagline.setObjectName("brandTagline")
    tagline.setAlignment(Qt.AlignCenter)

    column = QVBoxLayout()
    column.setSpacing(10)
    column.addWidget(mark_row_wrap, alignment=Qt.AlignHCenter)
    column.addWidget(tagline)

    wrapper = QWidget()
    wrapper.setLayout(column)
    return wrapper


def _build_bold_card(icon: str, title: str, description: str) -> QWidget:
    """One standalone bold callout card - filled with color_primary, the
    same "strongest visual anchor" tone the button system already uses,
    so it stays high-contrast against the page in either theme."""
    icon_box = QWidget()
    icon_box.setObjectName("boldSideIcon")
    icon_box.setFixedSize(34, 34)
    icon_layout = QVBoxLayout(icon_box)
    icon_layout.setContentsMargins(0, 0, 0, 0)
    icon_glyph = QLabel(icon)
    icon_glyph.setObjectName("boldSideIconGlyph")
    icon_layout.addWidget(icon_glyph)

    title_label = QLabel(title)
    title_label.setObjectName("boldSideTitle")
    title_label.setWordWrap(True)

    desc_label = QLabel(description)
    desc_label.setObjectName("boldSideDesc")
    desc_label.setWordWrap(True)

    card_layout = QVBoxLayout()
    card_layout.setContentsMargins(18, 18, 18, 18)
    card_layout.setSpacing(12)
    card_layout.addWidget(icon_box)
    card_layout.addWidget(title_label)
    card_layout.addWidget(desc_label)

    card = QWidget()
    card.setObjectName("boldSideCard")
    card.setFixedWidth(BOLD_CARD_WIDTH)
    card.setLayout(card_layout)
    apply_hard_shadow(card)
    return card


def _build_bold_column(cards: list[QWidget]) -> QWidget:
    """Vertically centers a stack of bold cards next to the login card."""
    layout = QVBoxLayout()
    layout.setSpacing(20)
    layout.addStretch()
    for card in cards:
        layout.addWidget(card)
    layout.addStretch()

    wrapper = QWidget()
    wrapper.setFixedWidth(BOLD_CARD_WIDTH)
    wrapper.setLayout(layout)
    return wrapper


class LoginWindow(QMainWindow):
    """Collects credentials and delegates authentication to AuthService.

    Emits login_succeeded(dict) with the AuthService user_data payload
    (including a session_token) on success. Never touches the database or
    password logic directly.
    """

    login_succeeded = Signal(dict)

    # Below this window width, the two flanking bold-card columns are
    # hidden (see _apply_responsive_layout) rather than left to crowd or
    # clip against the credentials card.
    SIDE_COLUMNS_MIN_WIDTH = 1360

    def __init__(self, auth_service: AuthService):
        super().__init__()
        self._auth_service = auth_service

        self.setWindowTitle(f"{PRODUCT_NAME} — Sign In")
        # The true floor: brand header + card alone, columns hidden - the
        # card's own vertical content (pill, heading, two fields, button,
        # error slot, footnote) needs ~740px of height with the header
        # above it, not the 640 an earlier pass guessed without measuring;
        # that guess left the footnote overlapping the card's bottom edge
        # at the window's own declared minimum size.
        self.setMinimumSize(640, 780)

        page = GridBackgroundWidget()
        page.setObjectName("background")

        card = QWidget()
        card.setObjectName("card")
        card.setFixedWidth(380)
        apply_hard_shadow(card)

        security_pill = QLabel("SECURE SIGN-IN")
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

        subtitle = QLabel("Sign in to access your dashboard")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)

        username_label = QLabel("USERNAME")
        username_label.setObjectName("fieldLabel")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")

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

        self.login_button = QPushButton("Sign In →")
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.setMinimumHeight(44)
        self.login_button.clicked.connect(self._attempt_login)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        footnote = QLabel("Locked out or need a password reset? Contact your system administrator.")
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

        # Card flanked by two bold callout cards, distributed two-per-side
        # rather than stacked in a single side panel (see module docstring).
        this_terminal_card = _build_bold_card(
            "🖥️",
            "This terminal",
            f"{get_device_info()} · {datetime.now().strftime('%A, %d %B %Y')}",
        )
        # Kept as attributes so resizeEvent() can show/hide them - the
        # actual sign-in card must never be the thing that gives way when
        # the window gets narrow, so these decorative columns are what
        # drops out instead (see resizeEvent below).
        self._left_column = _build_bold_column([_build_bold_card(*BOLD_FEATURES[0]), _build_bold_card(*BOLD_FEATURES[1])])
        self._right_column = _build_bold_column([_build_bold_card(*BOLD_FEATURES[2]), this_terminal_card])

        content_row = QHBoxLayout()
        content_row.setSpacing(0)
        content_row.addWidget(self._left_column)
        content_row.addStretch(1)
        content_row.addWidget(card)
        content_row.addStretch(1)
        content_row.addWidget(self._right_column)

        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(48, 40, 48, 40)
        page_layout.addStretch(1)
        page_layout.addWidget(_build_brand_header(), alignment=Qt.AlignHCenter)
        page_layout.addSpacing(36)
        page_layout.addLayout(content_row)
        page_layout.addStretch(1)
        page.setLayout(page_layout)

        self.setCentralWidget(page)

        self.username_input.setFocus()
        self._apply_responsive_layout()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        """The four bold callout cards are decoration, not content - below
        SIDE_COLUMNS_MIN_WIDTH there isn't room for both columns plus the
        card without either overlapping or squeezing the card's own
        breathing room away, so they're dropped rather than shrunk. The
        credentials card itself never resizes: it's what the screen exists
        to show, and it already fits down to the window's true minimum
        size (see setMinimumSize above)."""
        show_columns = self.width() >= self.SIDE_COLUMNS_MIN_WIDTH
        self._left_column.setVisible(show_columns)
        self._right_column.setVisible(show_columns)

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

        # Password verification (bcrypt) isn't instant, and the button is
        # still clickable while it runs - without this, a double-click
        # fires two concurrent authenticate() calls. Restored in every
        # exit path below, success included, since login_succeeded may
        # not swap this window out immediately.
        self.login_button.setEnabled(False)
        self.login_button.setText("Signing in…")
        try:
            success, user_data, error = self._auth_service.authenticate(
                username, password, device_info=get_device_info()
            )
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the login screen
            self._set_error(describe_unexpected_error(exc))
            return
        finally:
            self.login_button.setEnabled(True)
            self.login_button.setText("Sign In →")

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
