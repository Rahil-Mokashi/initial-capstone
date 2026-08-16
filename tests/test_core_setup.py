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


def test_main_creates_backups_and_reports_directories_on_startup(monkeypatch, tmp_path):
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

    assert os.path.isdir(tmp_path / "backups")
    assert os.path.isdir(tmp_path / "reports")


def test_init_db_takes_a_scheduled_backup_when_data_exists_and_none_is_recent(monkeypatch, tmp_path):
    from app.database.backup import list_backups
    from app.database.connection import init_db

    sqlite_path = str(tmp_path / "petrol_pump.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr("app.database.connection.DB_PATH", sqlite_path)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr(
        "app.database.connection.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False),
    )

    init_db()  # first run: creates the schema, file has no data yet beforehand - no scheduled backup expected
    assert list_backups(sqlite_path) == []

    init_db()  # second run: the file now has data and no backup is recent - a scheduled one should be taken
    backups = list_backups(sqlite_path)
    assert len(backups) == 1
    assert "scheduled" in backups[0].filename


def test_init_db_does_not_take_a_second_scheduled_backup_right_away(monkeypatch, tmp_path):
    from app.database.backup import list_backups
    from app.database.connection import init_db

    sqlite_path = str(tmp_path / "petrol_pump.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr("app.database.connection.DB_PATH", sqlite_path)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr(
        "app.database.connection.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False),
    )

    init_db()
    init_db()  # takes the first scheduled backup
    init_db()  # too soon for another one

    assert len(list_backups(sqlite_path)) == 1


def test_init_db_respects_configured_auto_backup_interval(monkeypatch, tmp_path):
    """AUTO_BACKUP_INTERVAL_HOURS used to be a hardcoded constant with no
    way to change it short of a rebuild - init_db() must read the
    configurable Settings.auto_backup_interval_hours instead."""
    from app.database.backup import list_backups
    from app.database.connection import init_db

    sqlite_path = str(tmp_path / "petrol_pump.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr("app.database.connection.DB_PATH", sqlite_path)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr(
        "app.database.connection.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False),
    )
    monkeypatch.setattr("app.core.config.settings.auto_backup_interval_hours", 0.0)

    init_db()  # first run: creates the schema, no backup expected yet
    init_db()  # second run: data exists, and a 0-hour interval means "always due"

    assert len(list_backups(sqlite_path)) == 1


def test_main_wraps_database_errors_in_a_clean_exception(monkeypatch):
    def boom():
        raise OperationalError("CREATE TABLE ...", {}, Exception("disk I/O error"))

    monkeypatch.setattr("app.core.logging.setup_logging", lambda: None)
    monkeypatch.setattr("app.main.init_db", boom)

    with pytest.raises(DatabaseInitializationError):
        main(run_ui=False)


def test_setup_logging_writes_a_file_next_to_the_database(monkeypatch, tmp_path):
    """Packaged builds run with console=False (petrol_pump_erp.spec), so a
    console-only logger leaves no record at all on a client's machine.
    setup_logging() must also attach a rotating file handler colocated
    with the database."""
    import logging as logging_module

    from app.core.logging import LOG_FILENAME, logger, setup_logging

    monkeypatch.setenv("PETROL_PUMP_DB_PATH", str(tmp_path / "petrol_pump.db"))

    setup_logging()
    try:
        logger.info("regression test log line")
        for handler in logging_module.getLogger().handlers:
            handler.flush()

        log_path = tmp_path / LOG_FILENAME
        assert log_path.exists()
        assert "regression test log line" in log_path.read_text(encoding="utf-8")
    finally:
        logging_module.getLogger().handlers.clear()


def test_setup_logging_does_not_crash_when_the_log_directory_is_unwritable(monkeypatch, tmp_path):
    unwritable_db_path = str(tmp_path / "does-not-exist" / "petrol_pump.db")
    monkeypatch.setattr("app.database.connection.DB_PATH", unwritable_db_path)
    monkeypatch.setattr("os.makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("permission denied")))

    from app.core.logging import setup_logging

    setup_logging()  # must not raise
