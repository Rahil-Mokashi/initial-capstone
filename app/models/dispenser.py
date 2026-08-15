import uuid

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from .base import Base, EntityMixin


class Dispenser(EntityMixin, Base):
    """Physical fuel dispenser unit that holds one or more nozzles (problemstatement.md #15).

    Minimal master-data model — full Dispenser/Nozzle CRUD and a
    management UI belong to Phase 8 (Nozzle Management). This is just
    enough to give Nozzle a real parent so Phase 7's shift/nozzle
    assignment workflow has something to assign against.
    """

    __tablename__ = "dispensers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(32), unique=True, nullable=False, index=True)

    nozzles = relationship("Nozzle", back_populates="dispenser")

    def __repr__(self) -> str:
        return f"<Dispenser(code={self.code!r})>"
