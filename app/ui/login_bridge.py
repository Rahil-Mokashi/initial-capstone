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

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.core.keyboard_state import is_caps_lock_on
from app.services.auth_service import AuthService
from app.ui.qt_utils import describe_unexpected_error
from app.ui.terminal_settings import get_login_locale, get_recent_usernames, record_recent_username, set_login_locale
from app.ui.theme import is_dark_mode, set_dark_mode


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
    pinChanged = Signal()
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
        self._pin = ""
        # Not a QML-visible Property with its own notify signal - see
        # setPinMode's docstring for why this is set only via a Slot
        # reached through the same queued-connection pattern as submit()
        # itself, never a direct property write from a live QML click.
        self._pin_mode = False

    @Property(str, notify=errorChanged)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=capsLockOnChanged)
    def capsLockOn(self) -> bool:
        return self._caps_lock_on

    @Slot(name="pollCapsLock")
    def pollCapsLock(self) -> None:
        """Re-checks Caps Lock's OS-level toggle state.

        Called from a QML `Timer` in LoginScreen.qml, not a Python-owned
        QTimer - a QObject like this bridge has no natural point in its
        own lifecycle where such a timer would ever be stopped (nothing
        here closes it the way a QWidget's own close() would), so a
        perpetual Python-side QTimer leaks for as long as the process
        runs. A QML Timer's lifetime is tied to the scene that owns it
        instead: it stops existing the moment LoginScreen.qml's root
        item is destroyed, exactly when LoginWindow itself closes -
        found the hard way when it wasn't done this way: every
        LoginBridge constructed in the test suite (dozens, across
        test_login_bridge.py and every UI test that opens a login
        screen) left one live 400ms-interval timer running for the rest
        of the process, which both slowed the full suite roughly 5x and
        produced cascading native "already deleted" widget-teardown
        crashes later in the run from the sheer number of live Qt
        objects competing for garbage collection (see conftest.py's own
        docstring on that exact failure mode).

        A Timer.onTriggered call into Python is a safe boundary to cross
        (unlike onAccepted/onClicked - see submit()'s own docstring):
        it runs from the event loop's own idle dispatch, the same
        "already back at the outermost frame" guarantee a
        Qt.QueuedConnection relies on, never nested inside a live
        Return/click native call stack.
        """
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

    @Property(str, constant=True)
    def initialLoginLocale(self) -> str:
        """This terminal's saved login-screen language (see
        app/ui/terminal_settings.py) - read once at construction; QML
        keeps its own copy from here and reports changes back via
        setLoginLocale, the same split responsibility recentUsernames/
        record_recent_username already has."""
        return get_login_locale()

    @Slot(str, name="setLoginLocale")
    def setLoginLocale(self, value: str) -> None:
        """Persists the login screen's own language choice for this
        terminal. Reached only via a Qt.QueuedConnection from
        LoginWindow (see its own wiring) - the language toggle button in
        LoginScreen.qml only ever touches a plain QML property in its
        own onClicked handler, the same safe pattern as pinMode/
        setPinMode."""
        set_login_locale(value)

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

    def _get_pin(self) -> str:
        return self._pin

    def _set_pin(self, value: str) -> None:
        value = value or ""
        if value != self._pin:
            self._pin = value
            self.pinChanged.emit()

    pin = Property(str, _get_pin, _set_pin, notify=pinChanged)

    @Slot(bool, name="setPinMode")
    def setPinMode(self, value: bool) -> None:
        """Records which credential submit() should check next time it
        runs - PIN or password.

        Deliberately a Slot reached only via a Qt.QueuedConnection from
        LoginWindow (see its own wiring), the exact same boundary rule
        `submit()`'s own docstring documents for the Sign In button:
        LoginScreen.qml's PIN/password toggle button only ever touches a
        plain QML property (`root.pinMode`) in its own onClicked handler,
        pure QML/JS with no Python call - this method is reached only
        once that property's own auto-generated changed signal reaches
        LoginWindow's queued connection, safely after the click event
        has fully finished being delivered.
        """
        self._pin_mode = value

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
        credential = self._pin if self._pin_mode else self._password
        credential_label = "PIN" if self._pin_mode else "password"
        self._set_error("")
        self._set_attempts_remaining(-1)
        self._set_lockout_seconds_remaining(0)

        if not username or not credential:
            self._set_error(f"Please enter both your username and {credential_label}.")
            return

        # Password/PIN verification isn't instant; `busy` disables the
        # Sign In button in QML for the same reason the old widget version
        # disabled it directly - so a double-click can't fire two
        # concurrent authenticate() calls.
        self._set_busy(True)
        try:
            authenticate = (
                self._auth_service.authenticate_with_pin if self._pin_mode else self._auth_service.authenticate
            )
            success, user_data, error = authenticate(username, credential, device_info=get_device_info())
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
