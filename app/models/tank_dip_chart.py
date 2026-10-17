"""A tank's dip chart: the oil company's table of dip (cm on the stick) against litres in the tank.

Rows are never edited or deleted. A new chart voids the rows of the old one (voided_at) and adds its own, so what the chart said on
any earlier day can still be told.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Numeric, String

from app.database.types import UtcDateTime

from .base import Base


class TankDipChartPoint(Base):
    __tablename__ = "tank_dip_chart_points"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tank_id = Column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    dip_cm = Column(Numeric(7, 1), nullable=False)
    litres = Column(Numeric(12, 3), nullable=False)
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    voided_at = Column(UtcDateTime, nullable=True, index=True)
