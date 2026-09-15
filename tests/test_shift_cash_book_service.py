from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all table metadata)
from app.core.constants import ShiftStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.shift_cash_book_repository import ShiftCashBookRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.schemas.shift_cash_book import ShiftCashBookRecord
from app.services.auth_service import AuthService
from app.services.shift_cash_book_service import ShiftCashBookService


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    sqlite_path = str(tmp_path / "test_cash_book.db")
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
        username=username, email=f"{username}@example.com",
        password_hash=hash_password("Passw0rd!"), role=role, is_active=True,
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
def accountant_id(db_session):
    seed_initial_data()
    return make_user(db_session, UserRole.ACCOUNTANT.value, "accountant1").id


@pytest.fixture()
def open_shift_id(db_session, admin_id):
    shift = Shift(shift_date=date.today(), shift_label="Morning", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(shift)
    db_session.commit()
    return shift.id


@pytest.fixture()
def auth_service(db_session):
    audit_repo = AuditLogRepository(db_session)
    return AuthService(UserRepository(db_session), audit_repo, UserSessionRepository(db_session))


@pytest.fixture()
def cash_book_service(db_session, auth_service):
    audit_repo = AuditLogRepository(db_session)
    return ShiftCashBookService(
        ShiftCashBookRepository(db_session), ShiftRepository(db_session), audit_repo, auth_service,
    )


def test_record_shift_cash_movements(cash_book_service, admin_id, open_shift_id):
    cash_book = cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=open_shift_id, advance_amount=Decimal("500"), final_amount=Decimal("1200")),
    )
    assert cash_book.advance_amount == Decimal("500.00")
    assert cash_book.final_amount == Decimal("1200.00")
    assert cash_book.recorded_by_id == admin_id


def test_advance_and_final_default_to_zero(cash_book_service, admin_id, open_shift_id):
    cash_book = cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=open_shift_id),
    )
    assert cash_book.advance_amount == Decimal("0.00")
    assert cash_book.final_amount == Decimal("0.00")


def test_negative_advance_rejected_by_schema():
    with pytest.raises(ValueError):
        ShiftCashBookRecord(shift_id="x", advance_amount=Decimal("-1"))


def test_cannot_record_cash_movements_for_a_shift_twice(cash_book_service, admin_id, open_shift_id):
    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=open_shift_id, advance_amount=Decimal("100")),
    )
    with pytest.raises(ConflictError):
        cash_book_service.record_shift_cash_movements(
            admin_id, ShiftCashBookRecord(shift_id=open_shift_id, advance_amount=Decimal("200")),
        )


def test_recording_for_unknown_shift_raises_not_found(cash_book_service, admin_id):
    with pytest.raises(NotFoundError):
        cash_book_service.record_shift_cash_movements(
            admin_id, ShiftCashBookRecord(shift_id="does-not-exist"),
        )


def test_accountant_cannot_record_cash_movements(cash_book_service, accountant_id, open_shift_id):
    """Reuses RECONCILIATION_MANAGE, not a new permission - Accountant
    doesn't hold that one any more than they hold reconciliation-manage
    itself (same actor/workflow-moment reasoning documented on the
    service)."""
    with pytest.raises(PermissionDeniedError):
        cash_book_service.record_shift_cash_movements(
            accountant_id, ShiftCashBookRecord(shift_id=open_shift_id),
        )


def test_get_for_shift_returns_the_recorded_cash_book(cash_book_service, admin_id, open_shift_id):
    cash_book_service.record_shift_cash_movements(
        admin_id, ShiftCashBookRecord(shift_id=open_shift_id, advance_amount=Decimal("300")),
    )
    fetched = cash_book_service.get_for_shift(admin_id, open_shift_id)
    assert fetched.advance_amount == Decimal("300.00")


def test_get_for_shift_returns_none_when_not_yet_recorded(cash_book_service, admin_id, open_shift_id):
    assert cash_book_service.get_for_shift(admin_id, open_shift_id) is None


def test_list_all_includes_every_recorded_cash_book(cash_book_service, admin_id, open_shift_id, db_session):
    other_shift = Shift(shift_date=date.today(), shift_label="Evening", opened_by_id=admin_id, status=ShiftStatus.OPEN.value)
    db_session.add(other_shift)
    db_session.commit()

    cash_book_service.record_shift_cash_movements(admin_id, ShiftCashBookRecord(shift_id=open_shift_id))
    cash_book_service.record_shift_cash_movements(admin_id, ShiftCashBookRecord(shift_id=other_shift.id))

    assert len(cash_book_service.list_all(admin_id)) == 2
