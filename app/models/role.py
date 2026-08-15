import uuid
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from .base import Base, EntityMixin
from .role_permission import role_permissions


class Role(EntityMixin, Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(String(512), nullable=True)

    users = relationship("User", back_populates="role")
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
