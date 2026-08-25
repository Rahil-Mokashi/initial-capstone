"""Local application alerts screen (problemstatement.md #43).

Presentation only. NotificationService owns which alerts exist and who
is allowed to see them; this file decides how they look.

The screen is deliberately read-only. There is no "dismiss" button
because there is nothing to dismiss: every alert here is recomputed from
live data each time the screen refreshes, so the way to clear one is to
fix what caused it (refill the tank, approve the expense, collect the
payment). See NotificationService's module docstring for why that is a
design decision rather than a missing feature.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import NotificationSeverity
from app.ui.qt_utils import apply_hard_shadow, describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget

# Kept next to the presentation code rather than on the enum: these are
# labels for a human reading a screen, not part of the domain vocabulary.
_SEVERITY_LABEL = {
    NotificationSeverity.CRITICAL: "NEEDS ATTENTION",
    NotificationSeverity.WARNING: "WORTH A LOOK",
    NotificationSeverity.INFO: "FOR INFORMATION",
}


class AlertCard(QWidget):
    """One alert: a coloured left edge, a title, a severity tag, detail.

    A plain QWidget subclass, so it needs WA_StyledBackground or its
    stylesheet background/border silently will not render - the Qt/QSS
    gotcha already documented for DashboardCard. Built-in widgets like
    QFrame do not need this; a bare QWidget does.
    """

    def __init__(self, notification, parent=None):
        super().__init__(parent)
        self.setObjectName("alertCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("tone", notification.severity.value)

        title = QLabel(notification.title)
        title.setObjectName("alertTitle")
        title.setWordWrap(True)

        tag = QLabel(_SEVERITY_LABEL[notification.severity])
        tag.setObjectName("alertTag")
        tag.setProperty("tone", notification.severity.value)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(title, stretch=1)
        header.addWidget(tag, alignment=Qt.AlignTop)

        detail = QLabel(notification.detail)
        detail.setObjectName("alertDetail")
        detail.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(detail)
        self.setLayout(layout)

        apply_hard_shadow(self)


class NotificationWindow(QWidget):
    def __init__(self, notification_service, actor_user_id: str):
        super().__init__()
        self._notification_service = notification_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Alerts")
        self.setMinimumSize(760, 560)

        title = QLabel("Alerts")
        title.setObjectName("title")

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("subtitle")
        self.summary_label.setWordWrap(True)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(self.refresh_button)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        # The alerts live inside a scroll area rather than a fixed column:
        # the list length depends entirely on how the business is doing
        # today, so it cannot be sized in advance.
        self._alerts_layout = QVBoxLayout()
        self._alerts_layout.setSpacing(12)
        self._alerts_layout.addStretch()

        alerts_container = QWidget()
        alerts_container.setObjectName("background")
        alerts_container.setLayout(self._alerts_layout)

        scroll = QScrollArea()
        scroll.setObjectName("background")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(alerts_container)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(top_row)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.error_label)
        layout.addWidget(scroll, stretch=1)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)

        self.refresh()

    def refresh(self) -> None:
        self.error_label.hide()
        try:
            summary = self._notification_service.get_notifications(self._actor_user_id)
        except Exception as exc:  # noqa: BLE001
            # NotificationService already isolates each producer, so
            # reaching here means something broader failed. Say so rather
            # than showing an empty list, which would read as "all clear".
            self.error_label.setText(describe_unexpected_error(exc))
            self.error_label.show()
            self.summary_label.setText("The alert list could not be loaded, so this screen is not showing all clear.")
            return

        self._clear_alerts()

        if summary.total == 0:
            self.summary_label.setText("")
            empty = QLabel(
                "Nothing needs your attention right now.\n\n"
                "Alerts appear here automatically when something changes — low stock, an unapproved "
                "expense, an overdue customer — and disappear again once it is dealt with."
            )
            empty.setObjectName("alertEmptyState")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            self._alerts_layout.insertWidget(0, empty)
            return

        self.summary_label.setText(
            f"{summary.total} alert(s): {summary.critical_count} needing attention, "
            f"{summary.warning_count} worth a look. "
            "An alert clears itself once the situation behind it is resolved."
        )
        for index, notification in enumerate(summary.notifications):
            self._alerts_layout.insertWidget(index, AlertCard(notification))

    def _clear_alerts(self) -> None:
        """Remove every card but keep the trailing stretch, so a short
        list stays top-aligned instead of spreading down the window.

        setParent(None) as well as deleteLater(): deleteLater only frees
        the widget on a later turn of the event loop, so until then the
        card is still a child of this window. Detaching it immediately
        means a refresh cannot briefly show the previous list underneath
        the new one, and it makes "the alert went away" observable the
        moment it is true rather than whenever Qt gets round to it.
        """
        while self._alerts_layout.count() > 1:
            item = self._alerts_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
