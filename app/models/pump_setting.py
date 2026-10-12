"""Owner-decision settings (site visit 2026-10-12): one row per key.

Anything the pump owner has not yet decided (rounding rule, whether testing
is added back, ...) is a setting with a safe default, never a hard-coded
rule. See app/services/pump_settings_service.py for the registry of keys.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String

from app.database.types import UtcDateTime

from .base import Base


class PumpSetting(Base):
    __tablename__ = "pump_settings"

    key = Column(String(64), primary_key=True)
    value = Column(String(512), nullable=False)
    updated_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    updated_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
