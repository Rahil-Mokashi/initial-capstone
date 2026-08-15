import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import DatabaseInitializationError
from app.main import main
from app.database.connection import DB_PATH, _default_database_path


def test_database_path_exists(tmp_path):
    db_file = tmp_path / "petrol_pump.db"
    assert str(db_file).endswith("petrol_pump.db")


def test_frozen_build_uses_per_user_app_data_dir_not_temp_extraction_path(monkeypatch, tmp_path):
    """A PyInstaller onefile build re-extracts to a fresh sys._MEIPASS on
    every launch, so resolving the DB path relative to this file's location
    (as a normal dev checkout does) would silently reset the database on
    every single start once packaged. When frozen, it must use a stable,
    writable per-user directory instead."""
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("PETROL_PUMP_DB_PATH", raising=False)

    path = _default_database_path()

    assert path == os.path.join(str(tmp_path), "PetrolPumpERP", "petrol_pump.db")
    assert os.path.isdir(os.path.join(str(tmp_path), "PetrolPumpERP"))


def test_env_override_takes_precedence_even_when_frozen(monkeypatch, tmp_path):
    from app.database.connection import get_database_path

    monkeypatch.setattr("sys.frozen", True, raising=False)
    override_path = str(tmp_path / "custom.db")
    monkeypatch.setenv("PETROL_PUMP_DB_PATH", override_path)

    assert get_database_path() == override_path


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


def test_main_wraps_database_errors_in_a_clean_exception(monkeypatch):
    def boom():
        raise OperationalError("CREATE TABLE ...", {}, Exception("disk I/O error"))

    monkeypatch.setattr("app.core.logging.setup_logging", lambda: None)
    monkeypatch.setattr("app.main.init_db", boom)

    with pytest.raises(DatabaseInitializationError):
        main(run_ui=False)
