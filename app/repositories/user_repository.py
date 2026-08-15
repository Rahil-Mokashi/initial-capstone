from sqlalchemy.orm import Session
from app.models.user import User
from app.repositories.base import safe_commit


class UserRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, user_id: str):
        return self._session.query(User).filter_by(id=user_id, is_deleted=False).first()

    def get_by_username(self, username: str):
        return self._session.query(User).filter_by(username=username, is_deleted=False).first()

    def add(self, user: User):
        self._session.add(user)
        safe_commit(self._session)
        self._session.refresh(user)
        return user

    def update(self, user: User):
        safe_commit(self._session)
        self._session.refresh(user)
        return user
