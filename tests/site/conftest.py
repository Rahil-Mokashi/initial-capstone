"""Fixtures for the site-visit build tests: a throwaway DB, seeded roles, and the
same Services container the API uses, so a test exercises the real wiring."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from api.services import Services
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.user import User


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.database.connection.engine", engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", factory)
    seed_initial_data()
    yield factory
    engine.dispose()


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def svc(db):
    return Services(db, 8)


def make_user(db, role_name: str, username: str) -> User:
    user = User(
        username=username, email=f"{username}@example.com", password_hash=hash_password("Passw0rd!x"),
        first_name=username.title(), last_name="Tester", role=db.query(Role).filter_by(name=role_name).first(),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def uid(db):
    """role name -> a user id of that role."""
    return {r.value: make_user(db, r.value, r.value.lower()).id for r in UserRole if r is not UserRole.ADMIN} | {
        "ADMIN": db.query(User).filter_by(username="admin").first().id
    }
