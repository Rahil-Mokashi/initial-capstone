"""Run slow work off the GUI thread.

problemstatement.md #44 is explicit and in bold: "Do heavy operations
outside the main UI thread. Never freeze the application while generating
a large report." Until this module existed the app had no threading at
all - PDF and Excel export, CSV export, print rendering, create_backup,
restore, PRAGMA integrity_check and every report query ran synchronously
inside a Qt slot.

Why that freezes the window, precisely: a GUI program is an event loop
that pulls events off a queue and dispatches them. Your slot is called
*by* that loop, so while it runs the loop is not running - no repaints,
no clicks, no keystrokes. Take five seconds writing a PDF and the window
is frozen for five seconds; take longer and Windows notices the app is
not draining its message queue and paints "Not Responding" over it. On a
busy forecourt that reads as "the system has crashed" and gets the
machine rebooted mid-transaction.

The GIL does not prevent this from working, despite the folklore. The GIL
is released around blocking I/O and around calls into C extensions, which
is exactly what this work is: SQLite's C library, file writes, ReportLab's
output. Threads buy nothing for pure-Python arithmetic and everything for
this.

USAGE

    run_in_background(
        self,
        lambda: self._backup_service.create_backup(user_id, reason),
        on_done=lambda path: self._show_success(path),
        on_error=lambda exc: self._show_error(exc),
        busy_widgets=[self.backup_now_button],
    )

THE RULE THAT MUST NOT BE BROKEN

The worker function runs on a pool thread and MUST NOT touch any widget.
Only the thread that created the QApplication may do that; painting is
not thread-safe and never will be, and violating it produces crashes that
are intermittent and appear far from the cause. Results come back through
a Qt signal, which Qt delivers as a *queued* connection because emitter
and receiver are on different threads - so the callbacks below run on the
GUI thread, where touching widgets is legal. That is thread-safety by
construction, with no locks in calling code.

A second rule specific to this app: a SQLAlchemy Session is not
thread-safe, so a worker doing database work needs its own Session and
must return plain data - never live ORM instances, which would lazy-load
from the wrong thread's session the moment the GUI touched them.
"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QApplication, QWidget

from app.core.logging import logger


def _is_alive(widget: QWidget) -> bool:
    """Whether the C++ object behind a PySide proxy still exists.

    shiboken6 ships with PySide6 and answers this directly. The fallback
    exists only so this module never becomes the reason the app fails to
    start if that internal module ever moves.
    """
    try:
        import shiboken6

        return bool(shiboken6.isValid(widget))
    except ImportError:  # pragma: no cover - defensive
        try:
            widget.isEnabled()
            return True
        except RuntimeError:
            return False


class _WorkerSignals(QObject):
    """Signals must live on a QObject; QRunnable is not one."""

    finished = Signal(object)
    failed = Signal(object)


class _Worker(QRunnable):
    def __init__(self, fn: Callable[[], object]):
        super().__init__()
        self._fn = fn
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - forwarded to the GUI thread
            # Logged here as well as forwarded, because an exception that
            # escapes a QRunnable has no Python frame above it to catch it.
            logger.exception("Background task failed: %s", exc)
            self.signals.failed.emit(exc)
            return
        self.signals.finished.emit(result)


def run_in_background(
    owner: QWidget,
    fn: Callable[[], object],
    on_done: Callable[[object], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    busy_widgets: Sequence[QWidget] = (),
    busy_cursor: bool = True,
) -> None:
    """Run fn on a worker thread; deliver the result on the GUI thread.

    busy_widgets are disabled for the duration and re-enabled afterwards,
    which is what stops a user starting the same backup four times by
    clicking an unresponsive-looking button repeatedly.

    The worker keeps a reference on `owner` because a QRunnable whose last
    Python reference is dropped can be garbage-collected while the pool is
    still running it (concept: PySide objects are proxies over C++ objects
    with independent lifetimes).
    """
    for widget in busy_widgets:
        widget.setEnabled(False)
    if busy_cursor:
        QApplication.setOverrideCursor(Qt.WaitCursor)

    worker = _Worker(fn)

    def _restore() -> None:
        for widget in busy_widgets:
            # A background task outlives the screen that started it if the
            # user closes the window while it runs. The Python proxy is
            # still referenced by this closure, but the C++ object it wraps
            # has been destroyed with its parent (concept: Qt owns widget
            # lifetime through the parent tree, independently of Python's
            # reference counting), and touching it raises
            # "Internal C++ object already deleted". Skipping a dead widget
            # is correct here: there is no longer a button to re-enable.
            if _is_alive(widget):
                widget.setEnabled(True)
        if busy_cursor:
            QApplication.restoreOverrideCursor()
        # Drop the reference now the task is done.
        tasks = getattr(owner, "_background_tasks", None)
        if tasks is not None and worker in tasks:
            tasks.remove(worker)

    def _handle_done(result: object) -> None:
        _restore()
        if on_done is not None:
            on_done(result)

    def _handle_failed(exc: object) -> None:
        _restore()
        if on_error is not None:
            on_error(exc)  # type: ignore[arg-type]

    worker.signals.finished.connect(_handle_done)
    worker.signals.failed.connect(_handle_failed)

    if not hasattr(owner, "_background_tasks"):
        owner._background_tasks = []
    owner._background_tasks.append(worker)

    QThreadPool.globalInstance().start(worker)


def wait_for_background_tasks(timeout_ms: int = 10_000) -> bool:
    """Block until the pool is idle. For tests and for shutdown, never for
    ordinary UI code - calling this from a slot reintroduces the exact
    freeze this module exists to prevent."""
    return QThreadPool.globalInstance().waitForDone(timeout_ms)

