"""Persistent alert strip (Part B, 2026-09-16) - always visible above the
content area, not hidden behind a click the way the Alerts button/dropdown
is. Reads NotificationService's output directly: this is the THIRD
consumer of that same computed list (after the dashboard's "Attention
Needed" section and the Alerts screen/dropdown), never a fourth source of
truth - MainWindow fetches once per refresh and hands the same
NotificationSummary to the badge and this strip (see
MainWindow.refresh_alert_badge).

Renders every alert as one self-contained, plain-language sentence - WHAT
went wrong, WHERE (the real tank/customer/employee/shift name a producer
already put in `title`/`detail`, never a bare id or enum name), and WHAT
TO DO about it (`Notification.action`). Deliberately NOT the client's own
Morex reference's shape ("225 Low Stock — HYDE - 20 LTR +223": a bare
count plus abbreviated names with no action) - see docs/reference/.

Does not fetch its own data. A widget constructed here must never call
NotificationService itself: this project has a documented, real crash
from computing notifications during MainWindow.__init__ (a garbage
collection landing inside SQLAlchemy's result processing while a
freshly-built Qt widget tree was still settling - see main_window.py's
own comment on refresh_alert_badge), so this strip starts in a neutral
placeholder state and is only ever populated via set_summary(), called
from the same deferred, proven-safe session-timer tick the alert badge
already uses.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def _sentence(notification) -> str:
    """The one self-contained line a non-technical reader needs: WHAT
    and WHERE (title/detail, which every NotificationService producer
    already writes in plain language with real names) followed by WHAT
    TO DO (action)."""
    parts = [notification.title.rstrip(".") + "."]
    if notification.detail:
        parts.append(notification.detail)
    if notification.action:
        parts.append(notification.action)
    return " ".join(parts)


def collapsed_summary_text(summary) -> str:
    """The single collapsed line shown before expanding - specific
    enough to matter on its own, never a bare count. One alert shows its
    full sentence directly; more than one names the single most urgent
    one by name alongside the total, e.g. "3 alerts need attention -
    most urgent: MS-16 is low on fuel." (adapted from the brief's own
    "3 tanks low on stock, most urgent: MS-16" example) rather than a
    bare "3 alerts"."""
    if summary is None:
        return "Checking for alerts…"
    if summary.total == 0:
        return "All clear — nothing needs attention right now."
    shown = [n for n in summary.notifications if not n.is_summary]
    if len(shown) == 1:
        return _sentence(shown[0])
    worst = shown[0] if shown else summary.notifications[0]
    plural = "alert" if summary.total == 1 else "alerts"
    return f"{summary.total} {plural} need attention — most urgent: {worst.title}."


class AlertStripLine(QWidget):
    """One alert inside the expanded list: its full sentence, clickable
    to navigate to the exact screen involved (see MainWindow's
    notification-click handling)."""

    clicked = Signal()

    def __init__(self, notification, parent=None):
        super().__init__(parent)
        self.setObjectName("alertStripLine")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("tone", notification.severity.value)
        self.setCursor(Qt.PointingHandCursor)

        label = QLabel(_sentence(notification))
        label.setObjectName("alertStripLineText")
        label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.addWidget(label)
        self.setLayout(layout)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AlertStrip(QWidget):
    """The strip itself: a collapsed summary line with a show/hide
    toggle, expanding to a scrollable list of every alert. Construction
    takes no data source - see module docstring for why - only
    `on_navigate(notification)`, called when an expanded line is clicked.
    """

    def __init__(self, on_navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("alertStrip")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._on_navigate = on_navigate
        self._expanded = False
        self._shown_count = 0

        self._summary_label = QLabel(collapsed_summary_text(None))
        self._summary_label.setObjectName("alertStripSummary")
        self._summary_label.setWordWrap(True)

        self._toggle_button = QPushButton("")
        self._toggle_button.setObjectName("alertStripToggle")
        self._toggle_button.setCursor(Qt.PointingHandCursor)
        self._toggle_button.clicked.connect(self._toggle)
        self._toggle_button.hide()

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        header_row.addWidget(self._summary_label, stretch=1)
        header_row.addWidget(self._toggle_button)

        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(8)

        list_container = QWidget()
        list_container.setLayout(self._list_layout)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("background")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setWidget(list_container)
        self._scroll.setMaximumHeight(260)
        self._scroll.hide()

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)
        layout.addLayout(header_row)
        layout.addWidget(self._scroll)
        self.setLayout(layout)

    def set_summary(self, summary) -> None:
        """Populate the strip from an already-fetched NotificationSummary
        (or None, on a failed fetch - the strip degrades to a neutral
        message rather than blocking the rest of the window)."""
        self._summary_label.setText(collapsed_summary_text(summary))

        if summary is None:
            tone = ""
        elif summary.critical_count:
            tone = "critical"
        elif summary.warning_count:
            tone = "warning"
        else:
            tone = ""
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)

        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        shown = [n for n in summary.notifications if not n.is_summary] if summary else []
        self._shown_count = len(shown)
        for notification in shown:
            line = AlertStripLine(notification)
            line.clicked.connect(lambda _checked=False, n=notification: self._navigate(n))
            self._list_layout.addWidget(line)

        self._toggle_button.setVisible(self._shown_count > 1)
        self._toggle_button.setText("Hide" if self._expanded else f"Show all {self._shown_count}")
        self._scroll.setVisible(self._expanded and self._shown_count > 1)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._toggle_button.setText("Hide" if self._expanded else f"Show all {self._shown_count}")
        self._scroll.setVisible(self._expanded and self._shown_count > 1)

    def _navigate(self, notification) -> None:
        self._expanded = False
        self._scroll.hide()
        self._toggle_button.setText(f"Show all {self._shown_count}")
        self._on_navigate(notification)
