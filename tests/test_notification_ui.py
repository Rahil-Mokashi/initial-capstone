"""UI tests for the alerts screen (problemstatement.md #43).

These assert on what the operator can actually see, because the whole
value of an alert is that somebody notices it. A service that computes
the right list behind a screen that shows "all clear" is worse than no
feature at all - it is actively reassuring about a problem.
"""

import pytest
from PySide6.QtWidgets import QLabel

from app.core.constants import NotificationCategory, NotificationSeverity
from app.services.notification_service import Notification, NotificationSummary
from app.ui.notification_window import AlertCard, NotificationWindow


class StubNotificationService:
    """A stub rather than a real service with a database.

    These tests are about presentation - severity colours, the empty
    state, the failure path. Wiring a full ten-repository service in
    would test NotificationService again (tests/test_notification_service.py
    already does that thoroughly) while making the UI assertions harder
    to read.
    """

    def __init__(self, notifications=None, raises=None):
        self._notifications = notifications or []
        self._raises = raises
        self.call_count = 0

    def get_notifications(self, actor_user_id):
        self.call_count += 1
        if self._raises:
            raise self._raises
        return NotificationSummary(notifications=list(self._notifications))


def make_notification(severity=NotificationSeverity.WARNING, title="Something happened", is_summary=False):
    return Notification(
        category=NotificationCategory.LOW_FUEL,
        severity=severity,
        title=title,
        detail="Some explanatory detail.",
        is_summary=is_summary,
    )


def alert_cards(window):
    return window.findChildren(AlertCard)


def card_texts(window) -> list[str]:
    return [label.text() for card in alert_cards(window) for label in card.findChildren(QLabel)]


def test_alerts_are_displayed(qtbot):
    service = StubNotificationService([make_notification(title="T1 is low on fuel")])
    window = NotificationWindow(service, "user-1")
    qtbot.addWidget(window)

    assert len(alert_cards(window)) == 1
    assert "T1 is low on fuel" in card_texts(window)


def test_every_alert_gets_its_own_card(qtbot):
    service = StubNotificationService(
        [make_notification(title=f"Alert {index}") for index in range(4)]
    )
    window = NotificationWindow(service, "user-1")
    qtbot.addWidget(window)

    assert len(alert_cards(window)) == 4


def test_severity_is_carried_onto_the_card_for_styling(qtbot):
    """The stylesheet colours the card from this property, so if it is
    not set the operator sees a critical alert rendered exactly like an
    informational one."""
    service = StubNotificationService(
        [
            make_notification(severity=NotificationSeverity.CRITICAL, title="Critical"),
            make_notification(severity=NotificationSeverity.INFO, title="Info"),
        ]
    )
    window = NotificationWindow(service, "user-1")
    qtbot.addWidget(window)

    tones = {card.property("tone") for card in alert_cards(window)}
    assert tones == {"critical", "info"}


def test_the_summary_line_reports_the_counts(qtbot):
    service = StubNotificationService(
        [
            make_notification(severity=NotificationSeverity.CRITICAL),
            make_notification(severity=NotificationSeverity.WARNING),
            make_notification(severity=NotificationSeverity.WARNING),
        ]
    )
    window = NotificationWindow(service, "user-1")
    qtbot.addWidget(window)

    text = window.summary_label.text()
    assert "3 alert(s)" in text
    assert "1 needing attention" in text
    assert "2 worth a look" in text


def test_a_clean_system_shows_a_reassuring_empty_state(qtbot):
    window = NotificationWindow(StubNotificationService([]), "user-1")
    qtbot.addWidget(window)

    assert alert_cards(window) == []
    empty = window.findChild(QLabel, "alertEmptyState")
    assert empty is not None
    assert "Nothing needs your attention" in empty.text()


def test_a_failure_says_so_rather_than_showing_all_clear(qtbot):
    """The dangerous failure mode for an alert screen is silence. If the
    list cannot be produced, the screen must not look identical to a
    system with nothing wrong."""
    window = NotificationWindow(
        StubNotificationService(raises=RuntimeError("database is locked")), "user-1"
    )
    qtbot.addWidget(window)

    assert window.error_label.isVisible() or window.error_label.text() != ""
    assert "not showing all clear" in window.summary_label.text()
    assert alert_cards(window) == []


def test_refresh_recomputes_the_list(qtbot):
    """Alerts are derived, never stored, so refreshing must go back to
    the service rather than redisplaying a cached list."""
    service = StubNotificationService([make_notification()])
    window = NotificationWindow(service, "user-1")
    qtbot.addWidget(window)
    assert service.call_count == 1

    window.refresh()
    assert service.call_count == 2
    # And the screen must not have accumulated a second copy of the card.
    assert len(alert_cards(window)) == 1


def test_resolved_alerts_disappear_on_refresh(qtbot):
    """The behaviour that justifies deriving alerts instead of storing
    them: fixing the underlying problem clears the alert, with nothing
    to expire and nothing to mark as read."""
    service = StubNotificationService([make_notification(title="T1 is low on fuel")])
    window = NotificationWindow(service, "user-1")
    qtbot.addWidget(window)
    assert len(alert_cards(window)) == 1

    service._notifications = []
    window.refresh()

    assert alert_cards(window) == []


@pytest.mark.parametrize(
    "severity,expected",
    [
        (NotificationSeverity.CRITICAL, "NEEDS ATTENTION"),
        (NotificationSeverity.WARNING, "WORTH A LOOK"),
        (NotificationSeverity.INFO, "FOR INFORMATION"),
    ],
)
def test_severity_is_labelled_in_plain_language(qtbot, severity, expected):
    """A pump operator is not reading an enum. The label has to say what
    to do about it, which is also why none of them say "ERROR"."""
    window = NotificationWindow(StubNotificationService([make_notification(severity=severity)]), "user-1")
    qtbot.addWidget(window)

    assert expected in card_texts(window)
