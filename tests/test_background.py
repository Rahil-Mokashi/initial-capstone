"""Slow work runs off the GUI thread and reports back on it.

problemstatement.md #44: "Do heavy operations outside the main UI thread.
Never freeze the application while generating a large report."
"""

import threading
import time

import pytest
from PySide6.QtWidgets import QPushButton, QWidget

from app.ui.background import run_in_background, wait_for_background_tasks


@pytest.fixture()
def widget(qtbot):
    w = QWidget()
    qtbot.addWidget(w)
    return w


def test_the_worker_runs_on_a_different_thread_than_the_gui(widget, qtbot):
    """The whole point: if it ran on the GUI thread the window would freeze."""
    gui_thread = threading.current_thread().ident
    seen = {}

    run_in_background(widget, lambda: seen.setdefault("worker", threading.current_thread().ident))
    qtbot.waitUntil(lambda: "worker" in seen, timeout=5000)

    assert seen["worker"] != gui_thread


def test_the_result_is_delivered_back_on_the_gui_thread(widget, qtbot):
    """Callbacks touch widgets, so they MUST arrive on the GUI thread.
    Qt guarantees this by delivering cross-thread signals as queued
    connections."""
    gui_thread = threading.current_thread().ident
    got = {}

    run_in_background(
        widget,
        lambda: "payload",
        on_done=lambda r: got.update(value=r, thread=threading.current_thread().ident),
    )
    qtbot.waitUntil(lambda: "value" in got, timeout=5000)

    assert got["value"] == "payload"
    assert got["thread"] == gui_thread


def test_a_failure_is_routed_to_on_error_not_raised_into_the_event_loop(widget, qtbot):
    """An exception escaping a QRunnable has no Python frame above it and
    can abort the process, so it must be caught and forwarded."""
    failures = []

    def boom():
        raise ValueError("backup device unavailable")

    run_in_background(widget, boom, on_error=failures.append)
    qtbot.waitUntil(lambda: bool(failures), timeout=5000)

    assert isinstance(failures[0], ValueError)
    assert "backup device unavailable" in str(failures[0])


def test_busy_widgets_are_disabled_during_the_task_and_restored_after(widget, qtbot):
    """Stops a user starting the same backup four times by clicking an
    unresponsive-looking button repeatedly."""
    button = QPushButton(widget)
    done = []

    run_in_background(
        widget, lambda: time.sleep(0.2), on_done=done.append, busy_widgets=[button]
    )
    assert not button.isEnabled(), "button was not disabled while the task ran"

    qtbot.waitUntil(lambda: bool(done), timeout=5000)
    assert button.isEnabled(), "button was not re-enabled after the task"


def test_a_failed_task_still_restores_the_busy_widgets(widget, qtbot):
    """Otherwise one error leaves the screen permanently unusable."""
    button = QPushButton(widget)
    failures = []

    def boom():
        raise RuntimeError("nope")

    run_in_background(widget, boom, on_error=failures.append, busy_widgets=[button])
    qtbot.waitUntil(lambda: bool(failures), timeout=5000)
    assert button.isEnabled()


def test_several_tasks_can_run_without_losing_one(widget, qtbot):
    results = []
    for i in range(5):
        run_in_background(widget, lambda i=i: i * 2, on_done=results.append)
    qtbot.waitUntil(lambda: len(results) == 5, timeout=5000)
    assert sorted(results) == [0, 2, 4, 6, 8]
    assert wait_for_background_tasks(2000)
