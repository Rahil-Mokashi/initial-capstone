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

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.services.auth_service import AuthService
from app.ui.qt_utils import describe_unexpected_error
from app.ui.theme import is_dark_mode


def get_device_info() -> str:
    return platform.node() or "unknown-device"


class LoginBridge(QObject):
    errorChanged = Signal()
    busyChanged = Signal()
    usernameChanged = Signal()
    passwordChanged = Signal()
    loginSucceeded = Signal(dict)

    def __init__(self, auth_service: AuthService, parent=None):
        super().__init__(parent)
        self._auth_service = auth_service
        self._error = ""
        self._busy = False
        self._username = ""
        self._password = ""

    @Property(str, notify=errorChanged)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

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

    @Property(bool, constant=True)
    def darkMode(self) -> bool:
        return is_dark_mode()

    def _set_error(self, text: str) -> None:
        text = text or ""
        if text != self._error:
            self._error = text
            self.errorChanged.emit()

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

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
            return

        self.loginSucceeded.emit(user_data)
