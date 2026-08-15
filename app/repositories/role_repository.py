from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.role import Role


class RoleRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, role_id: str) -> Optional[Role]:
        return self._session.query(Role).filter_by(id=role_id).first()

    def get_by_name(self, name: str) -> Optional[Role]:
        return self._session.query(Role).filter_by(name=name).first()

    def list_all(self) -> List[Role]:
        return self._session.query(Role).order_by(Role.name).all()
