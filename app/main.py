import sys

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import DatabaseInitializationError
from app.core.logging import logger, setup_logging
from app.core.paths import ensure_app_directories
from app.database.connection import init_db
from app.database.seed import seed_initial_data


def _initialize_database() -> None:
    """Create/seed the database, translating low-level failures into a
    single typed exception the caller can present cleanly instead of a
    raw traceback (problemstatement.md #43: "Database error" notification)."""
    try:
        init_db()
        seed_initial_data()
        ensure_app_directories()
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Database initialization failed", exc_info=True)
        raise DatabaseInitializationError(
            f"Could not initialize the database at startup: {exc}. "
            "Check that the database file/directory exists, is writable, and is not corrupted."
        ) from exc


def main(run_ui: bool = True) -> None:
    """Entry point for the Petrol Pump ERP application."""
    setup_logging()
    _initialize_database()

    print("Petrol Pump ERP initialized successfully.")
    print(f"Environment: {settings.environment}")

    if run_ui:
        try:
            from app.ui.main_window import launch_app
        except ImportError:
            print("PySide6 is not installed. Run `pip install -r requirements.txt` to enable the GUI.")
            return
        launch_app()


if __name__ == "__main__":
    try:
        main()
    except DatabaseInitializationError as exc:
        print(f"Fatal: {exc}")
        sys.exit(1)
