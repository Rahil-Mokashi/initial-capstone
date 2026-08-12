from app.core.config import settings
from app.database.connection import init_db
from app.core.logging import setup_logging


def main() -> None:
    """Entry point for the Petrol Pump ERP application."""
    setup_logging()
    init_db()
    print("Petrol Pump ERP initialized successfully.")
    print(f"Environment: {settings.environment}")


if __name__ == "__main__":
    main()
