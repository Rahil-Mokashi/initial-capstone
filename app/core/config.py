from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "sqlite:///./petrol_pump.db"
    session_timeout_hours: int = 8
    log_level: str = "INFO"
    secret_key: str = "change-me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
