"""Support screen (2026-08-25) - the reference design's "Support" tab.

Deliberately static: no business logic, no service dependency. Unlike the
reference mockup's fictional 24/7 hotline and hardware-telemetry contacts
(this app has no such infrastructure - it is a single-machine offline
desktop app with no vendor support line), the content here points at
things that are actually true of this application: where backups live,
who to ask for an account problem, and that everything works without an
internet connection by design.

Visible to every logged-in user (no permission gate), the same "always
reachable" treatment My Shift and Change Password get.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.qt_utils import apply_hard_shadow
from app.ui.widgets import GridBackgroundWidget


class _SupportCard(QWidget):
    def __init__(self, heading: str, body: str, tone: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        heading_label = QLabel(heading)
        heading_label.setObjectName("sectionTitle")

        body_label = QLabel(body)
        body_label.setObjectName("subtitle")
        body_label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)
        layout.addWidget(heading_label)
        layout.addWidget(body_label)
        self.setLayout(layout)

        apply_hard_shadow(self)


class SupportWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        title = QLabel("Support")
        title.setObjectName("title")

        subtitle = QLabel("Where to look and who to ask when something isn't working.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        offline_card = _SupportCard(
            "This app works fully offline",
            "PetrolPumpERP runs entirely on this machine - no internet connection, cloud service, or "
            "remote server is involved in day-to-day use. A connectivity problem on this device is never "
            "the cause of a screen not loading; a database or printer problem is a more likely place to look.",
        )

        account_card = _SupportCard(
            "Account or access problem",
            "Locked out, need a password reset, or need a role/permission changed? An Admin or Owner "
            "can unlock, reset, or reassign your account from Users. If you don't know who that is at "
            "your pump, ask your shift manager.",
        )

        backup_card = _SupportCard(
            "Lost or corrupted data",
            "Every backup taken by this app - manual or automatic - is listed on the Backups screen, "
            "along with an integrity check and restore. The off-device backup folder (a USB drive or "
            "network location) is set on the Settings screen and is the only protection against a "
            "failed disk, theft, or ransomware on this machine.",
        )

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        cards_row.addWidget(account_card)
        cards_row.addWidget(backup_card)

        body = QVBoxLayout()
        body.setContentsMargins(24, 24, 24, 24)
        body.setSpacing(20)
        body.addWidget(title)
        body.addWidget(subtitle)
        body.addWidget(offline_card)
        body.addLayout(cards_row)
        body.addStretch()

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(body)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)
