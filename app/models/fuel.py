import uuid
from sqlalchemy import Column, String, Float, Boolean
from .base import Base, EntityMixin


class Fuel(EntityMixin, Base):
    __tablename__ = "fuels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fuel_type = Column(String(128), nullable=False, index=True)
    rate_per_liter = Column(Float, nullable=False, default=0.0)
    capacity = Column(Float, nullable=False, default=0.0)
    current_stock = Column(Float, nullable=False, default=0.0)
    opening_stock = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, default=True, nullable=False)
