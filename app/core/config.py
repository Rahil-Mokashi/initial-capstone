from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Database location is deliberately not here - it has one real
    resolution path (app/database/connection.py's get_database_path(),
    which handles the frozen-build/dev/PETROL_PUMP_DB_PATH-override
    cases) rather than two competing ones."""

    environment: str = "development"
    session_timeout_hours: int = 8
    log_level: str = "INFO"

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
