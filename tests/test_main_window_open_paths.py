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
    from app.ui.main_window import AppController

    seed_initial_data()

    controller = AppController()
    success, user_data, error = controller._auth_service.authenticate(
        "admin", "Admin@123", device_info="test-main-window-open-paths",
    )
    assert success, f"login failed in fixture setup: {error}"

    controller._show_main_window(user_data)
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


def test_every_module_opens_through_its_real_menu_action(main_window):
    """The broad net: for every _open_* action a fully-permissioned
    Admin can reach, invoke it exactly as a click would and confirm it
    actually embeds a page - not a hand-picked subset of "the ones we
    remembered to check", every single one MainWindow currently defines.
    A clean pass here is worth recording on its own, not just a failure."""
    openers = _discover_module_openers(main_window)
    assert len(openers) >= 15, f"suspiciously few openers discovered: {openers}"

    failures = []
    for name in openers:
        try:
            getattr(main_window, name)()
        except Exception as exc:  # noqa: BLE001 - collecting every failure, not stopping at the first
            failures.append(f"{name}: {exc!r}")
            continue
        if main_window._content_stack.currentWidget() is None:
            failures.append(f"{name}: opened without raising, but no page is on screen")

    assert not failures, "module(s) failed to open through their real menu action:\n" + "\n".join(failures)


def test_reconciliation_opens_through_its_real_menu_action(main_window):
    """The specific regression this bug was: MainWindow._open_reconciliation
    referenced self._cash_book_service/self._employee_shortage_service,
    neither ever wired from AppController. Named separately from the
    broad-net test above so this exact regression stays easy to find."""
    main_window._open_reconciliation()

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
