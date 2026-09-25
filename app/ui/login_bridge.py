"""QObject exposed to app/ui/qml/LoginScreen.qml as the `bridge` context
property (wired in app/ui/login_window.py).

All authentication logic still lives in AuthService, exactly as it did
before the QML rewrite (2026-09-02) - this class only adapts that same
call into the property/signal shape QML's declarative bindings need
(a `busy` flag the Sign In button binds its enabled/label state to, an
`error` string the error banner binds its visibility/text to), so no
business rule moved and no rule was duplicated in QML/JS.

BOUNDARY-LEVEL DESIGN (2026-09-16, user-reported crash): `username`/
`password` are real, writable Qt Properties that QML keeps in sync
continuously (`onTextChanged`, on every keystroke), and `submit()` takes
no arguments - it reads them from `self`, already in sync by the time it
runs. This is deliberate: nothing here is ever called directly from
inside a QML TextField's own `onAccepted`/Button's `onClicked` handler.
See LoginScreen.qml's own comment and `submit()`'s docstring for why -
the short version is that doing so reliably crashed with a genuine
native stack overflow, for a reason this investigation was never able
to pin down at the stack-frame level (no working debugger/dump tooling
was available in the environment it was diagnosed in), but was proven
by exhaustive behaviour testing to be a *boundary* problem, not a
timing one: four different deferral attempts (Python-side
`QTimer.singleShot` at two different points, QML-side `Qt.callLater` at
two different points) all failed to stop it identically, which is what
ruled out re-entrancy/timing as the mechanism and pointed at the
call boundary itself.
"""

import platform
from datetime import datetime, timezone

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from app.core.keyboard_state import is_caps_lock_on
from app.services.auth_service import AuthService
from app.ui.qt_utils import describe_unexpected_error
from app.ui.terminal_settings import get_recent_usernames, record_recent_username
from app.ui.theme import is_dark_mode, set_dark_mode

# How often the Caps Lock indicator is re-checked. Caps Lock is a toggle
# key with no Qt change-notification of its own (see
# app/core/keyboard_state.py's docstring) - polling is the only option,
# and this only needs to be fast enough to feel immediate to someone who
# just pressed it, not fast enough for anything performance-sensitive.
CAPS_LOCK_POLL_INTERVAL_MS = 400


def get_device_info() -> str:
    return platform.node() or "unknown-device"


def _seconds_until(iso_timestamp) -> int:
    """Whole seconds between now and an ISO timestamp AuthService
    returned, floored at 0 - used to seed the lockout countdown QML
    ticks down locally rather than polling Python every second. None
    (no timestamp - an administrator-applied lock with no auto-expiry,
    or no lockout at all) maps to 0, meaning "no countdown to show"."""
    if not iso_timestamp:
        return 0
    locked_until = datetime.fromisoformat(iso_timestamp)
    remaining = (locked_until - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(remaining))


class LoginBridge(QObject):
    errorChanged = Signal()
    busyChanged = Signal()
    usernameChanged = Signal()
    passwordChanged = Signal()
    loginSucceeded = Signal(dict)
    capsLockOnChanged = Signal()
    darkModeChanged = Signal()
    attemptsRemainingChanged = Signal()
    lockoutSecondsRemainingChanged = Signal()

    def __init__(self, auth_service: AuthService, parent=None):
        super().__init__(parent)
        self._auth_service = auth_service
        self._error = ""
        self._busy = False
        self._username = ""
        self._password = ""
        self._caps_lock_on = is_caps_lock_on()
        self._attempts_remaining = -1  # -1: unknown/not applicable yet
        self._lockout_seconds_remaining = 0

        # Polling, not a Qt key-event hook: Caps Lock's toggle state has
        # to be read from the OS (see keyboard_state.is_caps_lock_on),
        # and this way it also updates if the key is pressed while the
        # window doesn't have focus, not just while typing here.
        self._caps_lock_timer = QTimer(self)
        self._caps_lock_timer.setInterval(CAPS_LOCK_POLL_INTERVAL_MS)
        self._caps_lock_timer.timeout.connect(self._poll_caps_lock)
        self._caps_lock_timer.start()

    @Property(str, notify=errorChanged)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=capsLockOnChanged)
    def capsLockOn(self) -> bool:
        return self._caps_lock_on

    def _poll_caps_lock(self) -> None:
        current = is_caps_lock_on()
        if current != self._caps_lock_on:
            self._caps_lock_on = current
            self.capsLockOnChanged.emit()

    @Property(int, notify=attemptsRemainingChanged)
    def attemptsRemaining(self) -> int:
        return self._attempts_remaining

    @Property(int, notify=lockoutSecondsRemainingChanged)
    def lockoutSecondsRemaining(self) -> int:
        return self._lockout_seconds_remaining

    @Property(str, constant=True)
    def deviceName(self) -> str:
        return get_device_info()

    @Property("QStringList", constant=True)
    def recentUsernames(self) -> list:
        """This terminal's last few successfully-used usernames (see
        app/ui/terminal_settings.py) - fixed for the life of this screen,
        since a new one is only ever added after a successful login,
        which closes this screen anyway."""
        return get_recent_usernames()

    def _get_username(self) -> str:
        return self._username

    def _set_username(self, value: str) -> None:
        value = value or ""
        if value != self._username:
            self._username = value
            self.usernameChanged.emit()

    username = Property(str, _get_username, _set_username, notify=usernameChanged)

    def _get_password(self) -> str:
        return self._password

    def _set_password(self, value: str) -> None:
        value = value or ""
        if value != self._password:
            self._password = value
            self.passwordChanged.emit()

    password = Property(str, _get_password, _set_password, notify=passwordChanged)

    @Property(bool, notify=darkModeChanged)
    def darkMode(self) -> bool:
        return is_dark_mode()

    @Slot(name="toggleDarkMode")
    def toggleDarkMode(self) -> None:
        """Lets the login screen flip light/dark mode itself, not just the
        main window after signing in - saved through the same QSettings
        store app/ui/theme.py already uses, so the choice carries into the
        main window's own theme once the user does log in, rather than
        being undone the moment this screen closes."""
        set_dark_mode(not is_dark_mode())
        self.darkModeChanged.emit()

    def _set_error(self, text: str) -> None:
        text = text or ""
        if text != self._error:
            self._error = text
            self.errorChanged.emit()

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

    def _set_attempts_remaining(self, value: int) -> None:
        if value != self._attempts_remaining:
            self._attempts_remaining = value
            self.attemptsRemainingChanged.emit()

    def _set_lockout_seconds_remaining(self, value: int) -> None:
        if value != self._lockout_seconds_remaining:
            self._lockout_seconds_remaining = value
            self.lockoutSecondsRemainingChanged.emit()

    @Slot(name="submit")
    def submit(self) -> None:
        """Reads `self.username`/`self.password` - kept in sync
        continuously by QML's own `onTextChanged` handlers, not passed
        as call arguments - rather than accepting them as parameters,
        so the caller never needs to reach into the live QML scene at
        call time either.

        Must only ever be invoked via a `Qt.QueuedConnection` from
        LoginWindow (see its own wiring) - never connected or called
        with a direct/auto connection from a signal that can fire while
        a QML input event (the Return key, a button click) is still
        being delivered. LoginScreen.qml's `onAccepted`/`onClicked`
        handlers only ever touch a plain QML property
        (`root.submitTrigger`) - pure QML/JS, confirmed safe by
        extensive testing - and never call into Python directly; this
        method is reached only when that property's own auto-generated
        `submitTriggerChanged` signal reaches LoginWindow's queued
        connection, which Qt guarantees dispatches only after the
        original event has fully finished being delivered and the
        native call stack that carried it has unwound.
        """
        username = self._username.strip()
        password = self._password
        self._set_error("")
        self._set_attempts_remaining(-1)
        self._set_lockout_seconds_remaining(0)

        if not username or not password:
            self._set_error("Please enter both your username and password.")
            return

        # Password verification (bcrypt) isn't instant; `busy` disables the
        # Sign In button in QML for the same reason the old widget version
        # disabled it directly - so a double-click can't fire two
        # concurrent authenticate() calls.
        self._set_busy(True)
        try:
            success, user_data, error = self._auth_service.authenticate(
                username, password, device_info=get_device_info()
            )
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the login screen
            self._set_error(describe_unexpected_error(exc))
            return
        finally:
            self._set_busy(False)

        if not success:
            self._set_error(error or "Login failed.")
            details = user_data or {}
            self._set_attempts_remaining(details.get("attempts_remaining", -1))
            self._set_lockout_seconds_remaining(_seconds_until(details.get("locked_until")))
            return

        record_recent_username(username)
        self.loginSucceeded.emit(user_data)
