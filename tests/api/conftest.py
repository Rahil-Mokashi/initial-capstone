"""Fixtures for the HTTP API tests: a throwaway SQLite DB, seeded roles, one
user per role we need, and a TestClient that sends the launch secret."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from api.app import create_app
from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.employee import Employee
from app.models.fuel import Fuel
from app.models.role import Role
from app.models.user import User

from api_helpers import PASSWORD, SECRET, login


@pytest.fixture()
def secret():
    return SECRET


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api_test.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    # seed_initial_data() opens connection.SessionLocal; point it at the test DB.
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


def _make_user(db, role_name: str, username: str, must_change_password: bool = False) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password(PASSWORD),
        first_name=username.title(),
        last_name="Tester",
        role=db.query(Role).filter_by(name=role_name).first(),
        is_active=True,
        must_change_password=must_change_password,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def users(db):
    """username -> role: manager (view+manage), accountant (view only), attendant (no inventory access)."""
    _make_user(db, UserRole.ADMIN.value, "admin1")
    _make_user(db, UserRole.MANAGER.value, "manager1")
    _make_user(db, UserRole.ACCOUNTANT.value, "accountant1")
    _make_user(db, UserRole.ATTENDANT.value, "attendant1")
    _make_user(db, UserRole.OWNER.value, "owner1")
    _make_user(db, UserRole.DATA_ENTRY.value, "dataentry1")
    _make_user(db, UserRole.MANAGER.value, "newhire1", must_change_password=True)
    return ["manager1", "accountant1", "attendant1", "newhire1"]


@pytest.fixture()
def employee_id(db):
    employee = Employee(
        employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date(2026, 1, 1),
    )
    db.add(employee)
    db.commit()
    return employee.id


@pytest.fixture()
def fuel_id(db):
    fuel = db.query(Fuel).first()
    if fuel is None:
        fuel = Fuel(fuel_type="Petrol", rate_per_liter=100)
        db.add(fuel)
        db.commit()
    return fuel.id


@pytest.fixture()
def client(session_factory, users):
    app = create_app(SECRET, session_factory=session_factory, session_timeout_hours=8)
    with TestClient(app, base_url="http://127.0.0.1", headers={"X-Launch-Secret": SECRET}) as c:
        yield c


@pytest.fixture()
def manager(client):
    return login(client, "manager1")


@pytest.fixture()
def admin(client):
    return login(client, "admin1")


@pytest.fixture()
def accountant(client):
    return login(client, "accountant1")


@pytest.fixture()
def owner(client):
    return login(client, "owner1")


@pytest.fixture()
def data_entry(client):
    return login(client, "dataentry1")


@pytest.fixture()
def attendant(client):
    return login(client, "attendant1")


@pytest.fixture()
def tank(client, manager, fuel_id):
    resp = client.post(
        "/api/tanks",
        headers=manager,
        json={"code": "T1", "fuel_id": fuel_id, "capacity": "10000", "opening_stock": "2500.5"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
