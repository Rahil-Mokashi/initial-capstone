"""User management UI (problemstatement.md #6, #39): create login accounts
for any of the six business roles, multiple users per role. Pure
presentation — validation and business rules live in UserService and its
Pydantic schema.
"""

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.exceptions import AppError
from app.schemas.user import UserCreate
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error, make_edit_icon_button
from app.ui.widgets import GridBackgroundWidget

USER_HEADERS = ["Username", "Email", "Role", "Status", ""]


def _status_text(user) -> str:
    if user.is_locked:
        return "Locked"
    if not user.is_active:
        return "Inactive"
    return "Active"


class UserListWindow(QWidget):
    def __init__(self, user_service, role_repo, actor_user_id: str):
        super().__init__()
        self._user_service = user_service
        self._role_repo = role_repo
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Users")
        self.setMinimumSize(760, 540)

        title = QLabel("Users")
        title.setObjectName("title")

        self.add_button = QPushButton("+ Add User")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._open_add_dialog)

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(self.add_button)

        self.table = QTableWidget(0, len(USER_HEADERS))
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(USER_HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(top_row)
        layout.addWidget(self.table)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(container)

        self.refresh()

    def refresh(self) -> None:
        users = self._user_service.list_users(self._actor_user_id)
        self.table.setRowCount(len(users))
        for row_index, user in enumerate(users):
            self.table.setItem(row_index, 0, QTableWidgetItem(user.username))
            self.table.setItem(row_index, 1, QTableWidgetItem(user.email))
            self.table.setItem(row_index, 2, QTableWidgetItem(user.role.name if user.role else ""))
            self.table.setItem(row_index, 3, QTableWidgetItem(_status_text(user)))
            self.table.item(row_index, 0).setData(Qt.UserRole, user.id)
            self.table.setCellWidget(
                row_index, 4, make_edit_icon_button(lambda _=False, uid=user.id: self._open_user(uid))
            )
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _open_add_dialog(self) -> None:
        dialog = UserFormDialog(self._user_service, self._role_repo, self._actor_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _open_user(self, user_id: str) -> None:
        dialog = UserDetailDialog(self._user_service, self._role_repo, self._actor_user_id, user_id, self)
        dialog.exec()
        self.refresh()


class UserFormDialog(QDialog):
    def __init__(self, user_service, role_repo, actor_user_id: str, parent=None):
        super().__init__(parent)
        self._user_service = user_service
        self._actor_user_id = actor_user_id

        self.setWindowTitle("Add User")
        self.setMinimumWidth(380)

        self.username_input = QLineEdit()
        self.email_input = QLineEdit()
        self.first_name_input = QLineEdit()
        self.last_name_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("At least 8 chars, upper/lower/digit")
        self.password_input.returnPressed.connect(self._save)

        chain_enter_to_next_field(
            self.username_input,
            self.email_input,
            self.first_name_input,
            self.last_name_input,
            self.password_input,
        )

        self.role_combo = QComboBox()
        for role in role_repo.list_all() if hasattr(role_repo, "list_all") else []:
            self.role_combo.addItem(role.name, role.id)

        form = QFormLayout()
        form.addRow("Username", self.username_input)
        form.addRow("Email", self.email_input)
        form.addRow("First name", self.first_name_input)
        form.addRow("Last name", self.last_name_input)
        form.addRow("Password", self.password_input)
        form.addRow("Role", self.role_combo)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _save(self) -> None:
        self.error_label.hide()
        if self.role_combo.count() == 0:
            self._show_error("No roles available.")
            return
        try:
            data = UserCreate(
                username=self.username_input.text(),
                email=self.email_input.text(),
                password=self.password_input.text(),
                role_id=self.role_combo.currentData(),
                first_name=self.first_name_input.text().strip() or None,
                last_name=self.last_name_input.text().strip() or None,
            )
            self._user_service.create_user(self._actor_user_id, data)
        except ValidationError as exc:
            self._show_error("; ".join(err["msg"] for err in exc.errors()))
            return
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


class UserDetailDialog(QDialog):
    def __init__(self, user_service, role_repo, actor_user_id: str, user_id: str, parent=None):
        super().__init__(parent)
        self._user_service = user_service
        self._role_repo = role_repo
        self._actor_user_id = actor_user_id
        self._user_id = user_id
        self._users_by_id = {u.id: u for u in user_service.list_users(actor_user_id)}
        self._user = self._users_by_id[user_id]

        self.setWindowTitle(self._user.username)
        self.setMinimumWidth(380)

        self.summary_label = QLabel(f"{self._user.username} — {self._user.email}")
        self.summary_label.setObjectName("sectionTitle")

        self.status_label = QLabel()

        self.role_combo = QComboBox()
        for role in role_repo.list_all():
            self.role_combo.addItem(role.name, role.id)
        if self._user.role:
            index = self.role_combo.findData(self._user.role.id)
            if index >= 0:
                self.role_combo.setCurrentIndex(index)
        change_role_button = QPushButton("Change Role")
        change_role_button.clicked.connect(self._change_role)

        role_row = QHBoxLayout()
        role_row.addWidget(self.role_combo, stretch=1)
        role_row.addWidget(change_role_button)

        self.toggle_active_button = QPushButton()
        self.toggle_active_button.setObjectName("secondaryButton")
        self.toggle_active_button.clicked.connect(self._toggle_active)

        self.unlock_button = QPushButton("Unlock Account")
        self.unlock_button.setObjectName("dangerButton")
        self.unlock_button.clicked.connect(self._unlock)

        self.reset_password_button = QPushButton("Reset Password")
        self.reset_password_button.setObjectName("secondaryButton")
        self.reset_password_button.clicked.connect(self._reset_password)

        close_button = QPushButton("Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.accept)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.addWidget(self.summary_label)
        layout.addWidget(self.status_label)
        layout.addLayout(role_row)
        layout.addWidget(self.toggle_active_button)
        layout.addWidget(self.unlock_button)
        layout.addWidget(self.reset_password_button)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

        self._refresh()

    def _refresh(self) -> None:
        self._users_by_id = {u.id: u for u in self._user_service.list_users(self._actor_user_id)}
        self._user = self._users_by_id[self._user_id]
        self.status_label.setText(f"Status: {_status_text(self._user)}")
        self.toggle_active_button.setText("Deactivate" if self._user.is_active else "Activate")
        self.unlock_button.setEnabled(self._user.is_locked)

    def _change_role(self) -> None:
        reason, ok = QInputDialog.getText(self, "Change role", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._user_service.change_user_role(
                self._actor_user_id, self._user_id, self.role_combo.currentData(), reason.strip()
            )
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not change role", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change role", describe_unexpected_error(exc))
        self._refresh()

    def _toggle_active(self) -> None:
        new_state = not self._user.is_active
        prompt = "Reason to deactivate:" if not new_state else "Reason to reactivate:"
        reason, ok = QInputDialog.getText(self, "Change status", prompt)
        if not ok or not reason.strip():
            return
        try:
            self._user_service.set_user_active(self._actor_user_id, self._user_id, new_state, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not change status", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not change status", describe_unexpected_error(exc))
        self._refresh()

    def _unlock(self) -> None:
        reason, ok = QInputDialog.getText(self, "Unlock account", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._user_service.unlock_user(self._actor_user_id, self._user_id, reason.strip())
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not unlock account", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not unlock account", describe_unexpected_error(exc))
        self._refresh()

    def _reset_password(self) -> None:
        new_password, ok = QInputDialog.getText(
            self, "Reset password", "New temporary password:", QLineEdit.Password
        )
        if not ok or not new_password:
            return
        reason, ok = QInputDialog.getText(self, "Reset password", "Reason:")
        if not ok or not reason.strip():
            return
        try:
            self._user_service.reset_password(self._actor_user_id, self._user_id, new_password, reason.strip())
            QMessageBox.information(
                self, "Password reset", "The user will be asked to set their own password on next login."
            )
        except (AppError, ValueError) as exc:
            QMessageBox.warning(self, "Could not reset password", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not reset password", describe_unexpected_error(exc))
        self._refresh()
