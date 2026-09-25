"""Self-service quick-sign-in PIN setup, reachable from the account menu
(app/ui/main_window.py) - mirrors app/ui/change_password_dialog.py's
shape exactly (re-enter the current password to prove identity, set the
new credential, one save action), since setting a PIN is the same kind
of self-service credential change as changing a password.
"""

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.core.constants import PIN_LENGTH
from app.core.exceptions import AppError
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error


class SetPinDialog(QDialog):
    def __init__(self, user_service, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._user_service = user_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Set a quick sign-in PIN")
        self.setMinimumWidth(380)

        layout = QVBoxLayout()

        notice = QLabel(
            f"A {PIN_LENGTH}-digit PIN lets you sign in faster on this device without typing "
            "your full password every time. It shares the same account lockout as your password."
        )
        notice.setWordWrap(True)
        notice.setObjectName("subtitle")
        layout.addWidget(notice)

        self.current_password_input = QLineEdit()
        self.current_password_input.setEchoMode(QLineEdit.Password)

        pin_validator = QRegularExpressionValidator(QRegularExpression(rf"\d{{0,{PIN_LENGTH}}}"))

        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setValidator(pin_validator)
        self.pin_input.setPlaceholderText(f"{PIN_LENGTH} digits")

        self.confirm_pin_input = QLineEdit()
        self.confirm_pin_input.setEchoMode(QLineEdit.Password)
        self.confirm_pin_input.setValidator(pin_validator)
        self.confirm_pin_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(self.current_password_input, self.pin_input, self.confirm_pin_input)

        form = QFormLayout()
        form.addRow("Current password", self.current_password_input)
        form.addRow("New PIN", self.pin_input)
        form.addRow("Confirm PIN", self.confirm_pin_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        save_button = QPushButton("Set PIN")
        save_button.clicked.connect(self._save)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        if self.pin_input.text() != self.confirm_pin_input.text():
            self._show_error("New PIN and confirmation do not match.")
            return
        try:
            self._user_service.set_own_pin(
                self._actor_user_id,
                self.current_password_input.text(),
                self.pin_input.text(),
            )
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
