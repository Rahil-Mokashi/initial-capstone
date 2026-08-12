import uuid
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from .base import Base, EntityMixin


class Role(EntityMixin, Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(String(512), nullable=True)

    users = relationship("User", back_populates="role")
