import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_audit_log_ui.db")
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", session_factory)

    session = session_factory()
    yield session
    session.close()


def make_user(db_session, role_name: str, username: str) -> User:
    role = db_session.query(Role).filter_by(name=role_name).first()
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_id(db_session):
    seed_initial_data()
    return db_session.query(User).filter_by(username="admin").first().id


@pytest.fixture()
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def user_repo(db_session):
    return UserRepository(db_session)


@pytest.fixture()
def audit_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return audit_repo, AuditService(audit_repo, auth_service)


def test_window_shows_recorded_events(qapp, audit_service, user_repo, admin_id):
    from app.ui.audit_log_window import AuditLogWindow

    audit_repo, service = audit_service
    audit_repo.record(event_type="tank_created", actor_id=admin_id, description="Created tank T1")

    window = AuditLogWindow(service, user_repo, admin_id)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "tank_created"


def test_event_type_filter_narrows_results(qapp, audit_service, user_repo, admin_id):
    from app.ui.audit_log_window import AuditLogWindow

    audit_repo, service = audit_service
    audit_repo.record(event_type="tank_created", actor_id=admin_id)
    audit_repo.record(event_type="user_created", actor_id=admin_id)

    window = AuditLogWindow(service, user_repo, admin_id)
    assert window.table.rowCount() == 2

    window.event_type_input.setText("tank")
    window.refresh()
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "tank_created"


def test_actor_filter_narrows_results(qapp, audit_service, user_repo, admin_id, attendant_id):
    from app.ui.audit_log_window import AuditLogWindow

    audit_repo, service = audit_service
    audit_repo.record(event_type="event_by_admin", actor_id=admin_id)
    audit_repo.record(event_type="event_by_attendant", actor_id=attendant_id)

    window = AuditLogWindow(service, user_repo, admin_id)
    assert window.table.rowCount() == 2

    index = window.actor_combo.findData(attendant_id)
    window.actor_combo.setCurrentIndex(index)
    window.refresh()

    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "event_by_attendant"


def test_window_raises_for_role_without_audit_view(qapp, audit_service, user_repo, attendant_id):
    from app.core.exceptions import PermissionDeniedError
    from app.ui.audit_log_window import AuditLogWindow

    _, service = audit_service
    with pytest.raises(PermissionDeniedError):
        AuditLogWindow(service, user_repo, attendant_id)
