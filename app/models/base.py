from datetime import datetime
from enum import Enum
from sqlalchemy import Column, DateTime, String, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class StatusEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    CANCELLED = "cancelled"


class EntityMixin:
    id = Column(String(36), primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    status = Column(String(32), default=StatusEnum.ACTIVE.value, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    name = Column(String(255), nullable=True)
