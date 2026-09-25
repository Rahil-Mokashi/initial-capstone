"""The main window's Lock Screen (reached via the account menu's "Lock"
action) - re-confirms the CURRENT user's identity to resume the same
session, without invalidating it the way Logout does. Distinct from
Logout in exactly that one way: a locked session is still the same
session (same session_token, same expiry clock), just visually blocked
behind this modal dialog until unlocked.

SECURITY NOTE on Windows Hello (app/core/windows_hello.py): it is only
ever offered here, never on the initial LoginScreen.qml sign-in. A
forecourt PC's Windows account is typically shared by the whole shift,
so a Windows Hello prompt proves only "the physical operator authenticated
to Windows" - it says nothing about which FuelDesk employee they are,
and using it as a substitute for that first identity check would
silently break the per-employee accountability AuthService's audit log
and lockout depend on. Here, identity was already fully established by
password/PIN at the ORIGINAL login; Windows Hello is only ever
re-confirming that the same physical operator is still present to
resume THAT SAME already-authenticated session - the same trust
boundary a phone banking app's Face ID unlock relies on, never a
substitute for its own first sign-in.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.core import windows_hello
from app.core.exceptions import AppError
from app.ui.qt_utils import describe_unexpected_error


class LockScreenDialog(QDialog):
    def __init__(self, auth_service, user_data: dict, parent=None):
        super().__init__(parent)
        self._auth_service = auth_service
        self._user_data = user_data
        # Set by "Sign Out Instead" - the caller (MainWindow._lock_screen)
        # checks this after exec() to decide whether to fully log out
        # rather than just resuming behind the dialog.
        self.signed_out = False

        display_name = user_data.get("first_name") or user_data["username"]

        self.setWindowTitle("Locked")
        self.setMinimumWidth(360)
        # No system close button - "Sign Out Instead" below is the
        # deliberate, visible way out, not an accidental Alt+F4/Esc.
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        layout = QVBoxLayout()

        title = QLabel(f"Welcome back, {display_name}")
        title.setObjectName("accountMenuName")
        layout.addWidget(title)

        subtitle = QLabel("Enter your password to resume where you left off.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._use_pin = False
        self.credential_input = QLineEdit()
        self.credential_input.setEchoMode(QLineEdit.Password)
        self.credential_input.returnPressed.connect(self._unlock)

        form = QFormLayout()
        self._credential_row_label = QLabel("Password")
        form.addRow(self._credential_row_label, self.credential_input)
        layout.addLayout(form)

        if user_data.get("has_pin"):
            pin_toggle = QPushButton("Use PIN instead")
            pin_toggle.setObjectName("secondaryButton")
            pin_toggle.clicked.connect(lambda: self._toggle_pin_mode(pin_toggle))
            layout.addWidget(pin_toggle)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        unlock_button = QPushButton("Unlock")
        unlock_button.clicked.connect(self._unlock)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(unlock_button)
        layout.addLayout(button_row)

        if windows_hello.is_available():
            hello_button = QPushButton("Unlock with Windows Hello")
            hello_button.setObjectName("secondaryButton")
            hello_button.clicked.connect(self._unlock_with_windows_hello)
            layout.addWidget(hello_button)

        sign_out_button = QPushButton("Sign Out Instead")
        sign_out_button.setObjectName("secondaryButton")
        sign_out_button.clicked.connect(self._sign_out_instead)
        layout.addWidget(sign_out_button)

        self.setLayout(layout)

    def reject(self) -> None:
        # No Escape-to-dismiss - "Sign Out Instead" is the deliberate way
        # out, matching ChangePasswordDialog's forced-mode reasoning.
        return

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.ignore()

    def _toggle_pin_mode(self, button: QPushButton) -> None:
        self._use_pin = not self._use_pin
        self._credential_row_label.setText("PIN" if self._use_pin else "Password")
        self.credential_input.clear()
        button.setText("Use password instead" if self._use_pin else "Use PIN instead")

    def _unlock(self) -> None:
        self.error_label.hide()
        credential = self.credential_input.text()
        if not credential:
            self._show_error(f"Please enter your {'PIN' if self._use_pin else 'password'}.")
            return
        try:
            success, error = self._auth_service.reauthenticate(
                self._user_data["id"], credential, use_pin=self._use_pin
            )
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        if not success:
            self.credential_input.clear()
            self._show_error(error or "Could not unlock.")
            return

        self.accept()

    def _unlock_with_windows_hello(self) -> None:
        if windows_hello.verify(f"Unlock Petrol Pump ERP as {self._user_data['username']}"):
            self.accept()
        else:
            self._show_error("Windows Hello could not verify you. Try your password or PIN instead.")

    def _sign_out_instead(self) -> None:
        self.signed_out = True
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
