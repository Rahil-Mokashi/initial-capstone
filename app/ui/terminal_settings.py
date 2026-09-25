"""Per-terminal display preferences for the login screen: which usernames
were last used to sign in on *this* machine, and which language the
login screen itself is shown in.

Stored via QSettings (the same store app/ui/theme.py already uses for
dark mode), not the app's own SQLite database — this is a convenience
for whoever is standing at this specific PC, not business data. It
carries no password/PIN, only usernames already visible to anyone
standing at the machine, so it needs no RBAC or audit trail, the same
reasoning theme.py's own docstring gives for dark mode.
"""

from PySide6.QtCore import QSettings

_SETTINGS_ORG = "PetrolPumpERP"
_SETTINGS_APP = "Desktop"
_RECENT_USERNAMES_KEY = "login/recent_usernames"
_LOGIN_LOCALE_KEY = "login/locale"

# How many recently-used usernames this terminal remembers. A shared
# forecourt PC is used by a handful of people across shifts, not dozens
# at once - three is enough to cover "who normally signs in here"
# without the list itself becoming a wall of names to scan.
MAX_RECENT_USERNAMES = 3


def get_recent_usernames() -> list[str]:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    value = settings.value(_RECENT_USERNAMES_KEY, [])
    if isinstance(value, str):
        # QSettings collapses a single-element list to a bare string on
        # some platforms/backends (the Windows registry backend among
        # them) - normalize back to a list rather than let a lone saved
        # username come back as an unusable non-list.
        return [value] if value else []
    return list(value or [])


def record_recent_username(username: str) -> None:
    """Move `username` to the front of this terminal's recent list,
    deduplicated, capped at MAX_RECENT_USERNAMES. Called only after a
    successful login - a failed attempt (possibly a typo, possibly not
    even a real account) never gets remembered."""
    username = (username or "").strip()
    if not username:
        return
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    existing = get_recent_usernames()
    updated = [username] + [name for name in existing if name != username]
    settings.setValue(_RECENT_USERNAMES_KEY, updated[:MAX_RECENT_USERNAMES])


def get_login_locale() -> str:
    """The login screen's own display language for this terminal -
    independent of the rest of the app, which is English-only today.
    Defaults to "en" whenever nothing has been saved yet."""
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    return settings.value(_LOGIN_LOCALE_KEY, "en", type=str)


def set_login_locale(locale: str) -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_LOGIN_LOCALE_KEY, locale)
