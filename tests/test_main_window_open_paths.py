"""Closes a real test gap (2026-09-15, user-requested): every existing
reconciliation UI test constructs ReconciliationWindow directly, never
going through MainWindow._open_reconciliation - the actual click path a
real user takes. That path referenced self._cash_book_service and
self._employee_shortage_service, neither of which MainWindow.__init__
ever accepted or AppController._show_main_window ever passed, so
opening the real "Reconciliation" menu item crashed with AttributeError
100% of the time, across two separate commits, with the full suite
green throughout.

This is the third time in this project a service-layer feature shipped
with no UI path actually reaching it that a test proved out (see
PROJECT_CONTEXT.md: testing_volume never wired into the assignment-
close screen, and the employee-shortage-recovery cash-book gap) - and
the first of the three that wasn't even a missing *feature*, just a
missing *wire*, which is arguably worse: nothing about it would show up
in a code review of the feature itself, only in a review of the two
places that are supposed to agree with each other (MainWindow's
constructor and AppController's call to it) and don't.

So this file constructs the real AppController -> real MainWindow ->
real _open_* method, the exact path a user's click takes, for every
module a broadly-permissioned role (Admin, who holds every Permission)
can reach - not a stand-in window built directly with hand-picked
services. It does not assert on screen content; proving the window
opens at all is the whole point, since that is exactly the step every
other reconciliation test skips.
"""
import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.database.seed import seed_initial_data

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def db_session(tmp_path_factory):
    """Module-scoped rather than the usual per-test fixture: building the
    real AppController -> MainWindow -> full dashboard is the expensive
    part of this file (every real service, every dashboard query), and
    all three tests below only read main_window's state, never mutate
    it in a way the others depend on not having happened - so paying
    that cost once instead of three times is a straightforward win, not
    a correctness compromise. monkeypatch itself is function-scoped, so
    app.database.connection's globals are patched/restored by hand."""
    import app.database.connection as db_connection

    sqlite_path = str(tmp_path_factory.mktemp("main_window_open_paths") / "test.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    original_engine, original_session_local = db_connection.engine, db_connection.SessionLocal
    db_connection.engine, db_connection.SessionLocal = engine, session_factory

    session = session_factory()
    yield session
    session.close()
    db_connection.engine, db_connection.SessionLocal = original_engine, original_session_local


@pytest.fixture(scope="module")
def main_window(qapp, db_session):
    """The real MainWindow, reached the same way a real login does -
    AppController built from scratch, then its own _show_main_window -
    not a MainWindow constructed by hand with a subset of services."""
    from PySide6.QtWidgets import QDialog

    from app.ui.main_window import AppController

    seed_initial_data()

    controller = AppController()
    success, user_data, error = controller._auth_service.authenticate(
        "admin", "Admin@123", device_info="test-main-window-open-paths",
    )
    assert success, f"login failed in fixture setup: {error}"

    # The seeded admin always starts with must_change_password=True (see
    # seed_initial_data), so _show_main_window would otherwise construct a
    # real, forced ChangePasswordDialog and block on its exec() here - not
    # a stand-in, an actual un-cancellable modal, since this fixture (unlike
    # test_change_password_opens_through_its_real_menu_action below) is
    # module-scoped and runs before any per-test monkeypatch exists. Patched
    # and restored by hand, the same way db_session handles its own globals,
    # rather than via monkeypatch (function-scoped; would revert before this
    # module-scoped fixture's later tests run, and the one test above that
    # genuinely exercises this dialog needs the real exec() until it applies
    # its own local patch).
    original_exec = QDialog.exec
    QDialog.exec = lambda self: QDialog.Accepted
    try:
        controller._show_main_window(user_data)
    finally:
        QDialog.exec = original_exec
    window = controller.main_window
    yield window
    window.close()


# _open_module_page/_push_subpage are the shared machinery every real
# opener calls into, not openers themselves. _open_change_password is
# the one opener that is a genuinely blocking modal (dialog.exec()) -
# tested separately below with exec() patched out, rather than folded
# into the generic loop where it would hang the test.
_NON_MODULE_OPENERS = {"_open_module_page", "_open_change_password"}


def _discover_module_openers(window) -> list:
    return sorted(
        name for name, _ in inspect.getmembers(window, predicate=inspect.ismethod)
        if name.startswith("_open_") and name not in _NON_MODULE_OPENERS
    )


# The (2026-09-16 navigation restructure) landing-page group openers - the
# top-level sidebar actions a fully-permissioned Admin can reach directly.
_LANDING_OPENERS = ("_open_masters_landing", "_open_operations_landing", "_open_settings_landing")


def _iter_card_group_tiles(main_window):
    """Every (group_label, item_title, factory) tile MainWindow._card_groups
    defines, flattened across subheadings - the same structure both the
    real sidebar/landing pages and this test read, so a module that exists
    in the app but was forgotten here is structurally impossible."""
    for group_label, subgroups in main_window._card_groups:
        for _subheading, entries in subgroups:
            for title, _subtitle, factory, _permission in entries:
                yield group_label, title, factory


_LANDING_OPENER_FOR_GROUP = {
    "MASTERS": "_open_masters_landing",
    "OPERATIONS": "_open_operations_landing",
    "SETTINGS": "_open_settings_landing",
}


def _open_grouped_module(main_window, group_label: str, item_title: str):
    """The real click path a grouped module now takes: open its group's
    landing page (as the sidebar row would), then drill into the tile
    (as a click on that tile would) - not a direct call that bypasses the
    landing page the wiring is actually supposed to go through."""
    getattr(main_window, _LANDING_OPENER_FOR_GROUP[group_label])()
    factory = next(
        factory
        for group, title, factory in _iter_card_group_tiles(main_window)
        if group == group_label and title == item_title
    )
    main_window._push_subpage(item_title, factory)


def test_every_top_level_action_opens_through_its_real_menu_action(main_window):
    """The broad net over what's left directly on the sidebar/top bar
    after the 2026-09-16 restructure: Masters/Operations/Settings land on
    their group page, Reports opens its own hub, Notifications and
    Support open their screens - not a hand-picked subset, every _open_*
    MainWindow currently defines outside the two exclusions above. A
    clean pass here is worth recording on its own, not just a failure."""
    openers = _discover_module_openers(main_window)
    assert len(openers) >= 5, f"suspiciously few top-level openers discovered: {openers}"

    failures = []
    for name in openers:
        try:
            getattr(main_window, name)()
        except Exception as exc:  # noqa: BLE001 - collecting every failure, not stopping at the first
            failures.append(f"{name}: {exc!r}")
            continue
        if main_window._content_stack.currentWidget() is None:
            failures.append(f"{name}: opened without raising, but no page is on screen")

    assert not failures, "action(s) failed to open through their real menu action:\n" + "\n".join(failures)


def test_every_grouped_module_opens_through_its_real_landing_page(main_window):
    """The broad net one level down: every module tile _card_groups
    defines (Employees, Tanks, Reconciliation, ...) is no longer reached
    by its own direct _open_* call - it is only reachable by opening its
    group's landing page and clicking through, so that is exactly the
    path this test drives, for every tile a fully-permissioned Admin can
    see, not a hand-picked subset."""
    tiles = list(_iter_card_group_tiles(main_window))
    assert len(tiles) >= 15, f"suspiciously few module tiles discovered: {tiles}"

    failures = []
    for group_label, item_title, _factory in tiles:
        try:
            _open_grouped_module(main_window, group_label, item_title)
        except Exception as exc:  # noqa: BLE001 - collecting every failure, not stopping at the first
            failures.append(f"{group_label} > {item_title}: {exc!r}")
            continue
        if main_window._content_stack.currentWidget() is None:
            failures.append(f"{group_label} > {item_title}: opened without raising, but no page is on screen")

    assert not failures, "module tile(s) failed to open through their real landing page:\n" + "\n".join(failures)


def test_reconciliation_opens_through_its_real_landing_page(main_window):
    """The specific regression this bug was: MainWindow._open_reconciliation
    (now the "Reconciliation" tile's factory under Operations) referenced
    self._cash_book_service/self._employee_shortage_service, neither ever
    wired from AppController. Named separately from the broad-net test
    above so this exact regression stays easy to find."""
    _open_grouped_module(main_window, "OPERATIONS", "Reconciliation")

    from app.ui.reconciliation_window import ReconciliationWindow

    page = main_window._content_stack.currentWidget()
    assert isinstance(page, ReconciliationWindow)
    # The two tabs that only render when their service was actually
    # passed through - proof this isn't just "didn't raise", but that
    # the services reached the window with real content attached.
    assert hasattr(page, "cash_book_tab")
    assert hasattr(page, "shortages_tab")


def test_change_password_opens_through_its_real_menu_action(main_window, monkeypatch):
    """_open_change_password's dialog.exec() is a genuinely blocking
    modal call, so exec() is patched out here rather than folded into
    the generic loop above, where it would hang the test suite. The
    thing actually at risk - the dialog's own construction reaching a
    missing service attribute - happens before exec() is ever called,
    so patching only exec() still exercises the real risk."""
    from PySide6.QtWidgets import QDialog

    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    main_window._open_change_password()


def test_opening_the_same_module_twice_leaves_only_one_instance_embedded(main_window):
    """2026-09-16, user-reported: opening a section from the sidebar
    briefly showed multiple windows on screen before settling.
    Diagnosed with a global Qt event filter (not just screenshots,
    which only catch whatever frame happens to be queried) - the flash
    turned out to be individual action buttons inside each page
    (Cancel Selected, + Add Tank, ...) briefly becoming their own
    independent top-level OS windows, not the page itself, and not
    duplicate page instances - see test_no_button_becomes_an_
    independent_window_while_opening_any_module below for that actual
    regression test.

    This test covers the other thing explicitly checked during
    diagnosis: MainWindow._open_module_page deliberately constructs a
    fresh instance on every single visit, by design (its own comment:
    "each visit still gets a fresh instance querying live data") - a
    second click on the same module is NOT expected to reuse the first
    instance, and this asserts that's still true (`is not`). What
    matters is that only one instance is ever actually embedded in
    _content_stack at a time - the previous one is removed and
    deleteLater()'d before the new one is added, never left to
    accumulate. Checked two ways: _content_stack's own count, and a
    real object-tree query (findChildren) after letting the queued
    deleteLater() actually run, so a regression that left the OLD
    widget as a hidden-but-still-parented straggler would be caught
    even though QStackedWidget.removeWidget() alone wouldn't show it.
    """
    from PySide6.QtWidgets import QApplication

    from app.ui.tank_window import TankListWindow

    _open_grouped_module(main_window, "MASTERS", "Tanks")
    first_widget = main_window._content_stack.currentWidget()
    stack_count_after_first = main_window._content_stack.count()
    assert isinstance(first_widget, TankListWindow)

    _open_grouped_module(main_window, "MASTERS", "Tanks")
    second_widget = main_window._content_stack.currentWidget()
    stack_count_after_second = main_window._content_stack.count()

    assert second_widget is not first_widget, (
        "each visit is deliberately a fresh instance (see _open_module_page's own comment) - "
        "this should be a NEW object, not the same one reused"
    )
    assert stack_count_after_second == stack_count_after_first, (
        "the old instance must be removed before the new one is added, not left to accumulate in the stack"
    )
    # 2, not 1: reaching a grouped module now always goes through its
    # landing page first (see _open_grouped_module), so the stack is
    # [landing page, Tanks] - the landing page from the PREVIOUS visit is
    # still expected to have been cleared by _open_masters_landing's own
    # _open_module_page call, which is exactly what the assertions above
    # already confirm (no accumulation).
    assert len(main_window._page_stack) == 2

    for _ in range(5):
        QApplication.processEvents()  # let the first instance's queued deleteLater() actually run

    remaining = main_window.findChildren(TankListWindow)
    assert remaining == [second_widget], (
        f"expected exactly one TankListWindow still alive in the widget tree after the second open, found {remaining}"
    )


def test_no_button_becomes_an_independent_window_while_opening_any_module(main_window, monkeypatch):
    """The actual regression test for the 2026-09-16 flicker bug.

    A widget constructed with no parent is, as far as Qt is concerned,
    its own independent top-level window - confirmed directly:
    QPushButton().setVisible(True) with no parent reports
    isWindow()=True, isVisible()=True, and a real screen-centered
    geometry. Every affected module built its permission-gated action
    buttons in the same order: construct -> setVisible(can_manage) ->
    *(added to a layout later)* -> self.setLayout(...) - so whenever
    can_manage was True, the button was a real, visible OS window for
    however long it took Qt to get around to the setLayout() call that
    actually parents it. Fixed across 10 files/~29 call sites by moving
    every one of those setVisible() calls to after its widget's
    setLayout() has already run.

    A test that only checks the state *after* a module finishes opening
    would never catch a regression of this specific kind - by the time
    __init__ returns, setLayout() has always already run regardless of
    what order the original bug had things in, so the end state looks
    identical either way. This instead patches QWidget.setVisible
    itself to record, at the exact moment of each call, whether the
    widget already had a parent - the only way to observe the ordering
    a regression would actually break, not just its (identical) final
    result.
    """
    from PySide6.QtWidgets import QDialog, QMainWindow, QWidget

    violations = []
    original_set_visible = QWidget.setVisible

    def recording_set_visible(self, visible):
        if visible and self.parent() is None and not isinstance(self, (QDialog, QMainWindow)):
            violations.append(f"{type(self).__name__}(text={getattr(self, 'text', lambda: '')()!r})")
        return original_set_visible(self, visible)

    monkeypatch.setattr(QWidget, "setVisible", recording_set_visible)

    # _discover_module_openers already excludes _open_change_password
    # (its dialog.exec() would hang here) - see its own test above.
    # Covers both levels: the top-level actions still on the sidebar/top
    # bar directly, and every grouped module tile one level down inside
    # its landing page - the flicker bug this regression-tests could
    # equally have lived in either.
    openers = _discover_module_openers(main_window)
    for name in openers:
        getattr(main_window, name)()
    for group_label, item_title, _factory in _iter_card_group_tiles(main_window):
        _open_grouped_module(main_window, group_label, item_title)

    assert not violations, (
        "widget(s) became visible while still parentless - i.e. briefly their own independent top-level "
        "window - during module navigation:\n" + "\n".join(violations)
    )


def _notification(category, title="Something needs attention"):
    from app.core.constants import NotificationSeverity
    from app.services.notification_service import Notification

    return Notification(category=category, severity=NotificationSeverity.WARNING, title=title, detail="Detail.")


# category -> the window class its alert strip click is supposed to land
# on. Deliberately covers every entry in MainWindow._NOTIFICATION_TARGETS
# plus both PENDING_APPROVAL branches, not a hand-picked subset - the
# same "prove every real wiring path, not just the ones remembered"
# principle the rest of this file already applies to menu actions.
@pytest.mark.parametrize(
    "category, title, expected_window_path",
    [
        ("LOW_FUEL", "Tank low", "app.ui.tank_window.TankListWindow"),
        ("FUEL_VARIANCE", "Variance", "app.ui.tank_window.TankListWindow"),
        ("CASH_SHORTAGE", "Cash short", "app.ui.reconciliation_window.ReconciliationWindow"),
        ("CASH_EXCESS", "Cash over", "app.ui.reconciliation_window.ReconciliationWindow"),
        ("PAYMENT_MISMATCH", "Payments", "app.ui.reconciliation_window.ReconciliationWindow"),
        ("FAILED_RECONCILIATION", "Needs approval", "app.ui.reconciliation_window.ReconciliationWindow"),
        ("ATTENDANCE_ISSUE", "No attendance", "app.ui.attendance_window.AttendanceWindow"),
        ("OUTSTANDING_CREDIT", "Overdue", "app.ui.credit_window.CreditWindow"),
        ("SUPPLIER_PAYMENT_DUE", "Invoice due", "app.ui.procurement_window.ProcurementWindow"),
        ("UNAUTHORIZED_ACTION", "Refused actions", "app.ui.audit_log_window.AuditLogWindow"),
        ("DATABASE_ERROR", "Integrity failed", "app.ui.audit_log_window.AuditLogWindow"),
        ("BACKUP_FAILURE", "No backup", "app.ui.backup_window.BackupWindow"),
        ("PENDING_APPROVAL", "3 expense(s) awaiting approval", "app.ui.expense_window.ExpenseWindow"),
        ("PENDING_APPROVAL", "2 shift reconciliation(s) awaiting approval", "app.ui.reconciliation_window.ReconciliationWindow"),
    ],
)
def test_clicking_an_alert_navigates_to_the_exact_screen_involved(main_window, category, title, expected_window_path):
    """Part B: "Clicking an alert navigates to the exact record or
    screen involved, not just the general module." Drives the real
    click-to-navigate method (MainWindow._navigate_to_notification)
    against the real MainWindow/content stack, for every category
    NotificationService can produce - not a hand test of the mapping
    dict in isolation, which would not catch a factory that raises or a
    title substring check that stops matching if a producer's wording
    ever changes.
    """
    import importlib

    from app.core.constants import NotificationCategory

    module_path, _, class_name = expected_window_path.rpartition(".")
    expected_window_class = getattr(importlib.import_module(module_path), class_name)

    notification = _notification(NotificationCategory[category], title=title)
    main_window._navigate_to_notification(notification)

    page = main_window._content_stack.currentWidget()
    assert isinstance(page, expected_window_class), (
        f"{category} ({title!r}) navigated to {type(page).__name__}, expected {class_name}"
    )
    # The real click path: a group landing page first, then a drill-down
    # with a breadcrumb back to it - not a shortcut with no way back.
    assert len(main_window._page_stack) == 2


# --------------------------------------------------------------------
# Top-bar current-shift indicator (problemstatement.md #36/#37) - the
# client-review pass, 2026-09-23. Placed last in this file deliberately:
# db_session and main_window are module-scoped and shared with every test
# above, and test_shift_indicator_reflects_a_real_open_shift below adds a
# real open Shift row to that shared database - safe for the tests above
# (none of them assert on shift counts), but ordered last anyway so nothing
# later in this file could be affected by it.
# --------------------------------------------------------------------


def test_shift_indicator_shows_no_shift_open_by_default(main_window):
    main_window.refresh_shift_indicator()
    assert main_window.shift_indicator_label.text() == "No shift open"
    assert main_window.shift_indicator_label.property("tone") in (None, "")


def test_shift_indicator_reflects_a_real_open_shift(main_window, db_session):
    from datetime import date

    from app.core.constants import ShiftStatus
    from app.models.shift import Shift

    shift = Shift(
        shift_date=date.today(), shift_label="Night",
        opened_by_id=main_window._user_data["id"], status=ShiftStatus.OPEN.value,
    )
    db_session.add(shift)
    db_session.commit()

    main_window.refresh_shift_indicator()
    assert main_window.shift_indicator_label.text() == "Shift: Night • Open"
    assert main_window.shift_indicator_label.property("tone") == "open"
