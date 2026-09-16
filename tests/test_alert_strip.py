"""Part B (2026-09-16): the persistent alert strip must render every
alert as one self-contained, plain-language WHAT/WHERE/WHAT-TO-DO
sentence, not a bare count or an abbreviated data dump (the client's own
Morex reference shows exactly that failure mode - see docs/reference/).

Uses hand-built Notification objects rather than a full DB-seeded
NotificationService pipeline: NotificationService's own business logic
(which alert fires under which condition) already has 31 passing tests
in test_notification_service.py. This file is about the presentation
layer only - given a Notification, does the strip actually read as a
sentence a non-technical person would understand.
"""

import pytest

from app.core.constants import NotificationCategory, NotificationSeverity
from app.services.notification_service import Notification, NotificationSummary
from app.ui.alert_strip import _sentence, collapsed_summary_text

pytest.importorskip("PySide6")


def _low_fuel_notification(severity=NotificationSeverity.CRITICAL) -> Notification:
    return Notification(
        category=NotificationCategory.LOW_FUEL,
        severity=severity,
        title="MS-16 is low on fuel",
        detail="450.00 of 5000.00 litres remaining (9% of capacity).",
        entity_id="tank-1",
        action="Reorder now — sales may have to stop once this tank runs out.",
    )


def _outstanding_credit_notification() -> Notification:
    return Notification(
        category=NotificationCategory.OUTSTANDING_CREDIT,
        severity=NotificationSeverity.WARNING,
        title="Arya Bus is overdue",
        detail="18500.00 outstanding, past the agreed 30-day term. Overdue is a signal to follow up, not an accusation.",
        entity_id="customer-1",
        action="Follow up with the customer, or open Credit to record a payment.",
    )


def _pending_expense_notification() -> Notification:
    return Notification(
        category=NotificationCategory.PENDING_APPROVAL,
        severity=NotificationSeverity.WARNING,
        title="3 expense(s) awaiting approval",
        detail="7433.00 in total is pending. Until approved, these do not reduce the expected cash in any shift reconciliation.",
        action="Open Expenses to review and approve the queue.",
    )


class TestSentenceFormat:
    """Every producer's title/detail/action must combine into one
    sentence naming the real thing (WHERE) and the real numbers (WHAT),
    never a bare enum/category name, plus a concrete next step."""

    def test_sentence_contains_what_where_and_what_to_do(self):
        notification = _low_fuel_notification()
        sentence = _sentence(notification)

        assert "MS-16" in sentence, "WHERE (the real tank name) must be in the sentence"
        assert "450.00" in sentence, "WHAT (the real numbers) must be in the sentence"
        assert "Reorder now" in sentence, "WHAT TO DO (a concrete next step) must be in the sentence"
        # Never the raw category/enum name - the whole point of the format.
        assert "LOW_FUEL" not in sentence
        assert "low_fuel" not in sentence

    def test_sentence_is_a_single_continuous_paragraph(self):
        """One self-contained line, not three disconnected fragments -
        the brief's own bad-example critique ("a bare count and
        abbreviated names") is exactly what this format must avoid."""
        sentence = _sentence(_outstanding_credit_notification())
        assert sentence.count("\n") == 0
        assert "Arya Bus" in sentence
        assert "18500.00" in sentence
        assert "open Credit" in sentence

    def test_sentence_degrades_gracefully_with_no_action(self):
        """A category without a recorded next step (shouldn't happen for
        any real producer, but the field defaults to "") still reads as
        a plain sentence rather than trailing off or raising."""
        notification = Notification(
            category=NotificationCategory.LOW_FUEL,
            severity=NotificationSeverity.INFO,
            title="Something happened",
            detail="Some detail.",
        )
        sentence = _sentence(notification)
        assert sentence == "Something happened. Some detail."


class TestCollapsedSummary:
    """The collapsed line is what a supervisor sees by default, without
    expanding anything - it must still be specific, never a bare number."""

    def test_no_summary_yet_shows_a_neutral_placeholder(self):
        assert "Checking" in collapsed_summary_text(None)

    def test_zero_alerts_reads_as_all_clear(self):
        summary = NotificationSummary(notifications=[])
        assert "All clear" in collapsed_summary_text(summary)

    def test_a_single_alert_shows_its_full_sentence_directly(self):
        notification = _low_fuel_notification()
        summary = NotificationSummary(notifications=[notification])
        assert collapsed_summary_text(summary) == _sentence(notification)

    def test_multiple_alerts_names_the_most_urgent_one_by_name(self):
        """Not just a bare "N alerts" - the collapsed line must name a
        real, specific alert even when there are several."""
        critical = _low_fuel_notification(NotificationSeverity.CRITICAL)
        warning = _outstanding_credit_notification()
        # Sorted the same way NotificationService itself sorts: critical first.
        summary = NotificationSummary(notifications=[critical, warning])

        text = collapsed_summary_text(summary)
        assert "2" in text
        assert critical.title in text, "must name the specific most-urgent alert, not just a count"

    def test_is_summary_trailer_lines_are_not_counted_as_real_alerts(self):
        """NotificationService's own "N more..." trailer (is_summary=True)
        is a footnote, not a distinct alert - the collapsed line must not
        treat it as the "single alert" case or count it as a name-worthy item."""
        real = _low_fuel_notification()
        trailer = Notification(
            category=NotificationCategory.LOW_FUEL,
            severity=NotificationSeverity.WARNING,
            title="4 more tanks running low",
            detail="4 further tanks running low are not shown here.",
            is_summary=True,
        )
        summary = NotificationSummary(notifications=[real, trailer])
        assert collapsed_summary_text(summary) == _sentence(real)


class TestAlertStripWidget:
    @pytest.fixture()
    def qapp(self):
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_expanding_shows_one_full_sentence_line_per_alert(self, qapp):
        from app.ui.alert_strip import AlertStrip

        notifications = [_low_fuel_notification(), _outstanding_credit_notification(), _pending_expense_notification()]
        summary = NotificationSummary(notifications=notifications)

        strip = AlertStrip(on_navigate=lambda n: None)
        strip.set_summary(summary)

        assert strip._list_layout.count() == 3
        for notification in notifications:
            found = any(
                _sentence(notification) in _line_text(strip._list_layout.itemAt(i).widget())
                for i in range(strip._list_layout.count())
            )
            assert found, f"expected a line reading: {_sentence(notification)!r}"

    def test_clicking_a_line_navigates_with_the_right_notification(self, qapp):
        from app.ui.alert_strip import AlertStrip

        notification = _outstanding_credit_notification()
        summary = NotificationSummary(notifications=[notification, _low_fuel_notification()])

        navigated = []
        strip = AlertStrip(on_navigate=navigated.append)
        strip.set_summary(summary)

        target_line = None
        for i in range(strip._list_layout.count()):
            widget = strip._list_layout.itemAt(i).widget()
            if _sentence(notification) in _line_text(widget):
                target_line = widget
                break
        assert target_line is not None
        target_line.clicked.emit()

        assert navigated == [notification]

    def test_a_single_alert_hides_the_expand_toggle(self, qapp):
        from app.ui.alert_strip import AlertStrip

        strip = AlertStrip(on_navigate=lambda n: None)
        strip.set_summary(NotificationSummary(notifications=[_low_fuel_notification()]))
        # isHidden() (the widget's own explicit shown/hidden flag), not
        # isVisible() (whether it's actually painted on screen) - this
        # strip is never .show()n in this test, so isVisible() would
        # read False regardless of what setVisible() was called with.
        assert strip._toggle_button.isHidden()

    def test_multiple_alerts_show_the_expand_toggle_with_a_real_count(self, qapp):
        from app.ui.alert_strip import AlertStrip

        strip = AlertStrip(on_navigate=lambda n: None)
        strip.set_summary(NotificationSummary(notifications=[_low_fuel_notification(), _outstanding_credit_notification()]))
        assert not strip._toggle_button.isHidden()
        assert "2" in strip._toggle_button.text()

    def test_a_failed_fetch_degrades_to_a_neutral_message_not_a_crash(self, qapp):
        from app.ui.alert_strip import AlertStrip

        strip = AlertStrip(on_navigate=lambda n: None)
        strip.set_summary(None)
        assert "Checking" in strip._summary_label.text()
        assert strip.property("tone") in ("", None)


def _line_text(line_widget) -> str:
    from PySide6.QtWidgets import QLabel

    return " ".join(label.text() for label in line_widget.findChildren(QLabel))
