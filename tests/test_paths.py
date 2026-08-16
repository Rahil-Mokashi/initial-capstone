import os

from app.core.paths import default_export_path, ensure_app_directories, get_backups_dir, get_logs_dir, get_reports_dir


def test_get_backups_dir_creates_and_returns_backups_subdir(monkeypatch, tmp_path):
    db_path = str(tmp_path / "petrol_pump.db")
    monkeypatch.setattr("app.database.connection.DB_PATH", db_path)

    backups_dir = get_backups_dir()

    assert backups_dir == str(tmp_path / "backups")
    assert os.path.isdir(backups_dir)


def test_get_reports_dir_creates_and_returns_reports_subdir(monkeypatch, tmp_path):
    db_path = str(tmp_path / "petrol_pump.db")
    monkeypatch.setattr("app.database.connection.DB_PATH", db_path)

    reports_dir = get_reports_dir()

    assert reports_dir == str(tmp_path / "reports")
    assert os.path.isdir(reports_dir)


def test_get_logs_dir_is_the_same_directory_as_the_database(monkeypatch, tmp_path):
    db_path = str(tmp_path / "petrol_pump.db")
    monkeypatch.setattr("app.database.connection.DB_PATH", db_path)

    assert get_logs_dir() == str(tmp_path)


def test_default_export_path_joins_reports_dir_with_filename(monkeypatch, tmp_path):
    db_path = str(tmp_path / "petrol_pump.db")
    monkeypatch.setattr("app.database.connection.DB_PATH", db_path)

    assert default_export_path("sales.pdf") == os.path.join(str(tmp_path), "reports", "sales.pdf")


def test_ensure_app_directories_creates_all_three(monkeypatch, tmp_path):
    db_path = str(tmp_path / "petrol_pump.db")
    monkeypatch.setattr("app.database.connection.DB_PATH", db_path)

    ensure_app_directories()

    assert os.path.isdir(tmp_path / "backups")
    assert os.path.isdir(tmp_path / "reports")
    assert os.path.isdir(tmp_path)
