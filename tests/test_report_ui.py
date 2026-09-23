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
from app.repositories.credit_account_repository import CreditAccountRepository
from app.repositories.customer_payment_repository import CustomerPaymentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_reconciliation_repository import ShiftReconciliationRepository
from app.repositories.nozzle_repository import NozzleRepository
from app.repositories.tank_repository import TankRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.repositories.tank_transaction_repository import TankTransactionRepository
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.shift_repository import ShiftRepository
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
        SaleRepository(db_session),
        PaymentRepository(db_session),
        ExpenseRepository(db_session),
        CreditAccountRepository(db_session),
        CustomerPaymentRepository(db_session),
        CustomerRepository(db_session),
        ShiftReconciliationRepository(db_session),
        TankTransactionRepository(db_session),
        AttendanceRepository(db_session),
        EmployeeRepository(db_session),
        ShiftRepository(db_session),
    )


def test_window_shows_seeded_fuel_types(qapp, qtbot, report_service, admin_id):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    # The fetch now runs on a worker thread (problemstatement.md #44), so
    # the cards appear when the task reports back rather than by the time
    # the constructor returns - see table_report_window.py's refresh for
    # the same pattern applied to the shared report window.
    # Petrol/Diesel/Power are seeded by default (DEFAULT_FUEL_TYPES).
    qtbot.waitUntil(lambda: window.cards_layout.count() >= 3, timeout=10000)


def test_export_pdf_writes_a_file(qapp, qtbot, report_service, admin_id, tmp_path, monkeypatch):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    target = tmp_path / "out.pdf"
    monkeypatch.setattr(
        "app.ui.report_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(target), "PDF Files (*.pdf)")
    )
    # Waiting on target.exists() is a race: ReportLab/openpyxl open (and
    # so create) the file before they finish writing to it, so "the file
    # exists" and "the file is complete" are different moments once the
    # write runs on a worker thread. Waiting for the "export complete"
    # dialog - which on_done only shows after export_fn has returned - is
    # what actually marks the write as finished.
    shown = {"called": False}
    monkeypatch.setattr("app.ui.report_window.QMessageBox.information", lambda *a, **k: shown.__setitem__("called", True))

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    window._export_pdf()

    qtbot.waitUntil(lambda: shown["called"], timeout=10000)
    assert target.exists()
    assert target.stat().st_size > 0


def test_export_excel_writes_a_file(qapp, qtbot, report_service, admin_id, tmp_path, monkeypatch):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    target = tmp_path / "out.xlsx"
    monkeypatch.setattr(
        "app.ui.report_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(target), "Excel Files (*.xlsx)")
    )
    shown = {"called": False}
    monkeypatch.setattr("app.ui.report_window.QMessageBox.information", lambda *a, **k: shown.__setitem__("called", True))

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    window._export_excel()

    qtbot.waitUntil(lambda: shown["called"], timeout=10000)
    assert target.exists()
    assert target.stat().st_size > 0


def test_export_csv_writes_a_file(qapp, qtbot, report_service, admin_id, tmp_path, monkeypatch):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    target = tmp_path / "out.csv"
    monkeypatch.setattr(
        "app.ui.report_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(target), "CSV Files (*.csv)")
    )
    shown = {"called": False}
    monkeypatch.setattr("app.ui.report_window.QMessageBox.information", lambda *a, **k: shown.__setitem__("called", True))

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    window._export_csv()

    qtbot.waitUntil(lambda: shown["called"], timeout=10000)
    assert target.exists()
    assert target.stat().st_size > 0


def test_export_cancelled_dialog_does_not_write_a_file(qapp, report_service, admin_id, monkeypatch):
    from app.ui.report_window import FuelTypeSummaryReportWindow

    monkeypatch.setattr("app.ui.report_window.QFileDialog.getSaveFileName", lambda *a, **k: ("", ""))

    window = FuelTypeSummaryReportWindow(report_service, None, admin_id)
    window._export_pdf()  # must not raise, must not prompt for anything further
    # No background task is dispatched when the dialog is cancelled (the
    # function returns before reaching run_in_background), so there is
    # nothing to wait for here - the assertion is simply that nothing
    # above raised.
