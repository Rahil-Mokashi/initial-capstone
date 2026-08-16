from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import UserRole
from app.core.exceptions import PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_audit.db")
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
def manager_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.MANAGER.value, "manager1").id


@pytest.fixture()
def attendant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ATTENDANT.value, "attendant1").id


@pytest.fixture()
def audit_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    auth_service = AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))
    return AuditService(audit_repo, auth_service)


def test_search_returns_recorded_events(audit_service, admin_id, db_session):
    audit_repo = AuditLogRepository(db_session)
    audit_repo.record(event_type="some_event", actor_id=admin_id)

    results = audit_service.search(admin_id)
    assert len(results) > 0


def test_manager_can_view_audit_log(audit_service, manager_id):
    results = audit_service.search(manager_id)
    assert isinstance(results, list)


def test_attendant_cannot_view_audit_log(audit_service, attendant_id):
    with pytest.raises(PermissionDeniedError):
        audit_service.search(attendant_id)


def test_search_filters_by_event_type(audit_service, admin_id, db_session):
    audit_repo = AuditLogRepository(db_session)
    audit_repo.record(event_type="tank_created", actor_id=admin_id, description="Test tank")

    results = audit_service.search(admin_id, event_type="tank_created")
    assert len(results) == 1
    assert results[0].event_type == "tank_created"


def test_search_filters_by_actor(audit_service, admin_id, manager_id, db_session):
    audit_repo = AuditLogRepository(db_session)
    audit_repo.record(event_type="test_event", actor_id=manager_id, description="By manager")

    results = audit_service.search(admin_id, filter_actor_id=manager_id)
    assert all(r.actor_id == manager_id for r in results)
    assert len(results) == 1


def test_search_filters_by_date_range_includes_today(audit_service, admin_id, db_session):
    audit_repo = AuditLogRepository(db_session)
    audit_repo.record(event_type="today_event", actor_id=admin_id)

    results = audit_service.search(admin_id, event_type="today_event", date_from=date.today(), date_to=date.today())
    assert len(results) == 1


def test_search_filters_by_date_range_excludes_other_days(audit_service, admin_id, db_session):
    audit_repo = AuditLogRepository(db_session)
    audit_repo.record(event_type="today_event", actor_id=admin_id)

    yesterday = date.today() - timedelta(days=1)
    results = audit_service.search(admin_id, event_type="today_event", date_from=yesterday, date_to=yesterday)
    assert len(results) == 0


def test_search_results_are_newest_first(audit_service, admin_id, db_session):
    audit_repo = AuditLogRepository(db_session)
    audit_repo.record(event_type="ordering_test", actor_id=admin_id, description="first")
    audit_repo.record(event_type="ordering_test", actor_id=admin_id, description="second")

    results = audit_service.search(admin_id, event_type="ordering_test")
    assert [r.description for r in results] == ["second", "first"]
