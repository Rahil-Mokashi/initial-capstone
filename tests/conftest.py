"""Shared pytest configuration.

Exists to hold one mitigation for a crash that has shaped this project's
CI for a while: running many Qt-constructing test modules in one process
aborts the interpreter with a Windows access violation, which is why
.github/workflows/tests.yml runs the suite in four batches instead of
one command.

The crash is always the same shape. The faulthandler traceback names
`Garbage-collecting` as the innermost frame, with SQLAlchemy immediately
below it - so the fault happens when Python's CYCLIC garbage collector
runs during ordinary ORM work, not in the ORM itself. That is a known
PySide6 failure mode: shiboken's Python wrappers for Qt objects
participate in reference cycles, so a collection pass can finalise a
wrapper whose C++ object is already gone, and dereference it.

`gc.freeze()` moves everything currently tracked into a permanent
generation the collector never examines again. Called after imports and
after the QApplication exists, it takes the large, long-lived population
of module objects and Qt type wrappers permanently out of the
collector's path. Objects created afterwards are still collected
normally, so this does not leak the things a test actually allocates -
it only stops the collector from repeatedly re-walking a graph that will
never become garbage anyway.

This does not make the underlying PySide6 behaviour correct, and it is
recorded as a mitigation rather than a fix.
"""

import gc

import pytest


@pytest.fixture(autouse=True)
def _no_blocking_message_boxes(monkeypatch):
    """Stop any modal QMessageBox from blocking the suite forever.

    QMessageBox's static helpers call exec() internally, so a UI method
    that reports an error through QMessageBox.warning() will sit waiting
    for a click that no test can make. That is not hypothetical: it was
    the cause of this suite's intermittent hang. A test stubbed
    QMessageBox.question but not QMessageBox.warning, then deliberately
    drove the failing path - and the run survived only when a queued
    event happened to dismiss the dialog, so it passed most of the time
    and stalled indefinitely the rest. Diagnosing that cost hours,
    because a silent hang produces no output to work from.

    Safe defaults are chosen so a leaked dialog cannot quietly approve
    something: acknowledgements return Ok, and any confirmation prompt
    returns No, meaning an unstubbed destructive action is DECLINED
    rather than performed. A test that needs a different answer still
    stubs it explicitly, and its own monkeypatch overrides this one.

    Deliberately limited to QMessageBox. QInputDialog is not stubbed
    here because its helpers return values the calling code then acts on
    (a reason string, a meter reading), so a blanket default would
    silently change what a test is exercising rather than just unblock
    it - those must be stubbed per test, where the value is visible.
    """
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:  # pragma: no cover - suite runs without Qt installed
        return

    for name, answer in (
        ("information", QMessageBox.Ok),
        ("warning", QMessageBox.Ok),
        ("critical", QMessageBox.Ok),
        ("about", None),
        ("question", QMessageBox.No),
    ):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, _r=answer, **k: _r), raising=False)


@pytest.fixture(autouse=True)
def _destroy_orphaned_widgets():
    """Close and delete every top-level widget a test left behind.

    THE root cause of the suite's native crashes, and worth stating
    plainly: 17 of the 20 UI test modules never use pytest-qt's `qtbot`.
    They build their own QApplication in a module-scoped fixture and then
    construct real windows inside test functions without registering them
    for cleanup, so nothing ever destroys them. Qt owns widget lifetime
    through the parent tree independently of Python reference counting,
    so a window whose last Python reference is dropped is NOT freed - it
    stays alive, along with its timers, its child widgets and (on the
    dashboard) a QGraphicsDropShadowEffect per card.

    Those accumulate for the whole session. The crash then lands wherever
    allocation happens to tip it over, which is why it looks random and
    appears to be caused by whatever change was made last rather than by
    the leak.

    Fixing it here rather than in the 17 files is deliberate: this is one
    reviewable place that also covers every UI test written in future,
    whereas retrofitting `qtbot.addWidget` across the suite is a large
    mechanical edit that would still be forgotten in the next new file.

    Runs after each test. processEvents() is what actually lets Qt act on
    the deferred deletions - without it deleteLater only queues them, and
    they would pile up exactly as before.
    """
    yield

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover - suite runs without Qt installed
        return

    app = QApplication.instance()
    if app is None:
        return

    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.setParent(None)
            widget.deleteLater()
        except RuntimeError:
            # Already destroyed by its own parent - normal here, not an error.
            continue
    app.processEvents()


@pytest.fixture(scope="session", autouse=True)
def _reduce_gc_pressure_from_qt_wrappers():
    # A full collection first, so genuine garbage from collection-time
    # imports is reclaimed rather than frozen in place forever.
    gc.collect()
    gc.freeze()
    yield
    # Deliberately NOT unfrozen.
    #
    # Calling gc.unfreeze() here was tried and made things worse: it
    # hands the entire frozen graph back to the collector at the exact
    # moment the session ends and Qt is tearing itself down, which
    # reintroduced the crash during interpreter shutdown - after every
    # test had already passed, so the run reported no failures while
    # still exiting non-zero. The process is about to exit and the
    # operating system reclaims the memory regardless, so there is
    # nothing to gain by unfreezing and a crash to lose.
