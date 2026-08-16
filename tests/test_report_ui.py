import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.fuel_reconciliation_repository import FuelReconciliationRepository
from app.repositories.fuel_repository import FuelRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.auth_service import AuthService
from app.services.report_service import ReportService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_report_ui.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def admin_id(db_session):
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def report_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return ReportService(
        FuelRepository(db_session),
        TankRepository(db_session),
        NozzleRepository(db_session),
        FuelReconciliationRepository(db_session),
        auth_service,
    )


def test_window_shows_seeded_fuel_types(qapp, report_service, admin_id):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    # Petrol/Diesel/Power are seeded by default (DEFAULT_FUEL_TYPES).
    assert window.cards_layout.count() >= 3


def test_export_pdf_writes_a_file(qapp, report_service, admin_id, tmp_path, monkeypatch):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    target = tmp_path / "out.pdf"
    monkeypatch.setattr(
        "app.ui.report_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(target), "PDF Files (*.pdf)")
    )
    monkeypatch.setattr("app.ui.report_window.QMessageBox.information", lambda *a, **k: None)

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    window._export_pdf()

    assert target.exists()
    assert target.stat().st_size > 0


def test_export_excel_writes_a_file(qapp, report_service, admin_id, tmp_path, monkeypatch):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    target = tmp_path / "out.xlsx"
    monkeypatch.setattr(
        "app.ui.report_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(target), "Excel Files (*.xlsx)")
    )
    monkeypatch.setattr("app.ui.report_window.QMessageBox.information", lambda *a, **k: None)

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    window._export_excel()

    assert target.exists()
    assert target.stat().st_size > 0


def test_export_cancelled_dialog_does_not_write_a_file(qapp, report_service, admin_id, monkeypatch):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    monkeypatch.setattr("app.ui.report_window.QFileDialog.getSaveFileName", lambda *a, **k: ("", ""))

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    window._export_pdf()  # must not raise, must not prompt for anything further
