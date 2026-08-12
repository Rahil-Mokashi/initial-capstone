from app.core.config import settings
from app.database.connection import init_db
from app.database.seed import seed_initial_data
from app.core.logging import setup_logging


def main(run_ui: bool = True) -> None:
    """Entry point for the Petrol Pump ERP application."""
    setup_logging()
    init_db()
    seed_initial_data()

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
    main()
