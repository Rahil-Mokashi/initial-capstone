import os
import sys

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


def _config_file_path() -> str:
    """Where an admin can drop a config file to change settings without a
    rebuild. Mirrors app/database/connection.py's frozen-build handling (a
    PyInstaller onefile build re-extracts to a new temp dir on every
    launch, so anything meant to persist must live in a stable per-user
    directory instead) - duplicated here in miniature rather than
    imported, since app.database.connection pulls in app.core.logging,
    which itself depends on this module; importing it here would be
    circular.
    """
    if getattr(sys, "frozen", False):
        base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base_dir, "PetrolPumpERP", "config.env")
    return ".env"


class Settings(BaseSettings):
    """Database location is deliberately not here - it has one real
    resolution path (app/database/connection.py's get_database_path(),
    which handles the frozen-build/dev/PETROL_PUMP_DB_PATH-override
    cases) rather than two competing ones.

    Editable without a rebuild: in a packaged build, drop a config.env
    file next to the database (%LOCALAPPDATA%\\PetrolPumpERP\\config.env)
    with lines like `SESSION_TIMEOUT_HOURS=12`; in a dev checkout, use
    .env in the project root instead. A real environment variable of the
    same name always takes precedence over either file.
    """

    environment: str = "development"
    session_timeout_hours: int = 8
    auto_backup_interval_hours: float = 24.0
    log_level: str = "INFO"

    model_config = ConfigDict(env_file=_config_file_path(), env_file_encoding="utf-8")


settings = Settings()
