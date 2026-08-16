"""Per-user directories this app writes to, all colocated with the
database (app/database/connection.py's get_database_path()) rather than
each deriving the frozen-build/dev-mode split independently. Created
eagerly on startup (app.main.main) so a fresh install has "backups",
"logs", and "reports" ready before the user ever triggers a backup or
export - not just lazily on first use.
"""

import os


def _app_data_dir() -> str:
    # Reads the module-global DB_PATH (not a fresh get_database_path()
    # call) for the same reason app.database.connection.init_db() does:
    # tests that monkeypatch app.database.connection.DB_PATH directly
    # must land in the path they actually intend, not the real default.
    from app.database import connection

    return os.path.dirname(connection.DB_PATH)


def get_backups_dir() -> str:
    path = os.path.join(_app_data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def get_logs_dir() -> str:
    # Same directory as the database - see app/core/logging.py. Exposed
    # here too so callers have one module to go to for every app-data
    # subdirectory rather than needing to know logging.py's internal path.
    path = _app_data_dir()
    os.makedirs(path, exist_ok=True)
    return path


def get_reports_dir() -> str:
    path = os.path.join(_app_data_dir(), "reports")
    os.makedirs(path, exist_ok=True)
    return path


def default_export_path(filename: str) -> str:
    """Where a report/receipt/statement export dialog should default to
    - a real folder the user can find again, not the last CWD."""
    return os.path.join(get_reports_dir(), filename)


def ensure_app_directories() -> None:
    get_backups_dir()
    get_logs_dir()
    get_reports_dir()
