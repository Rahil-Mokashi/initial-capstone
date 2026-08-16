import uuid

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from .base import Base, EntityMixin


class Nozzle(EntityMixin, Base):
    """A single nozzle on a dispenser, dispensing one fuel type (problemstatement.md #15).

    Minimal master-data model — see Dispenser's docstring for scope notes.
    Status values (active/inactive/maintenance) are NozzleStatus in
    app/core/constants.py, stored in EntityMixin's generic status column.
    """

    __tablename__ = "nozzles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(32), unique=True, nullable=False, index=True)
    dispenser_id = Column(String(36), ForeignKey("dispensers.id"), nullable=False, index=True)
    fuel_id = Column(String(36), ForeignKey("fuels.id"), nullable=False)
    # Which physical tank this nozzle draws from - nullable since a site
    # with only one tank per fuel type can leave it unset (SaleService
    # falls back to the single active tank for the nozzle's fuel type);
    # required to be explicit once a fuel type has more than one tank.
    tank_id = Column(String(36), ForeignKey("tanks.id"), nullable=True)

    dispenser = relationship("Dispenser", back_populates="nozzles")
    fuel = relationship("Fuel")
    tank = relationship("Tank")

    def __repr__(self) -> str:
        return f"<Nozzle(code={self.code!r}, status={self.status!r})>"
