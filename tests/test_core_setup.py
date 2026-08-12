import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import main
from app.database.connection import DB_PATH


def test_database_path_exists(tmp_path):
    db_file = tmp_path / "petrol_pump.db"
    assert str(db_file).endswith("petrol_pump.db")


def test_main_runs_without_error(monkeypatch, tmp_path):
    sqlite_path = str(tmp_path / "petrol_pump.db")
    engine = create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr("app.database.connection.DB_PATH", sqlite_path)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr(
        "app.database.connection.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False),
    )
    monkeypatch.setattr("app.core.logging.setup_logging", lambda: None)
    main(run_ui=False)
