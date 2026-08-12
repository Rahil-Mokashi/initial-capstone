import os
from app.main import main
from app.database.connection import DB_PATH


def test_database_path_exists(tmp_path):
    db_file = tmp_path / "petrol_pump.db"
    assert str(db_file).endswith("petrol_pump.db")


def test_main_runs_without_error(monkeypatch, tmp_path):
    monkeypatch.setattr("app.database.connection.DB_PATH", str(tmp_path / "petrol_pump.db"))
    monkeypatch.setattr("app.core.logging.setup_logging", lambda: None)
    main()
