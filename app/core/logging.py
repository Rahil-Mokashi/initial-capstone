import logging
import os
from logging.handlers import RotatingFileHandler

from app.core.config import settings

LOG_FILENAME = "petrol_pump_erp.log"
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5


def setup_logging() -> None:
    """Console logging alone is silent in the packaged build: the
    PyInstaller spec builds with console=False, so a StreamHandler has
    no window to write to, and the try/except-and-log-the-traceback
    pattern used throughout the UI (describe_unexpected_error) would
    leave no record at all on a client's machine after a crash. A
    rotating file, colocated with the database (same per-user app-data
    directory in a frozen build, same dev-mode location otherwise -
    see app/database/connection.py's path resolution), fixes that.
    """
    handlers = [logging.StreamHandler()]

    try:
        # Local import: app.database.connection imports this module's
        # `logger`, so importing it back at module load time here would
        # be circular - safe once setup_logging() is actually called.
        from app.database.connection import get_database_path

        log_dir = os.path.dirname(get_database_path())
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, LOG_FILENAME)
        handlers.append(
            RotatingFileHandler(log_path, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
        )
    except OSError:
        # A missing/unwritable log location must not block startup -
        # console-only logging is still better than crashing over it.
        pass

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
        force=True,
    )


logger = logging.getLogger("petrol_pump_erp")
