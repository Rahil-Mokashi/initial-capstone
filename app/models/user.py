import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from .base import Base, EntityMixin


class User(EntityMixin, Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=False, index=True)
    password_hash = Column(String(512), nullable=False)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    failed_attempts = Column(Integer, default=0, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    last_login = Column(DateTime, nullable=True)
    role_id = Column(String(36), ForeignKey("roles.id"), nullable=True)

    role = relationship("Role", back_populates="users")
