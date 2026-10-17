"""Entering and reading a tank's dip chart (centimetres on the dip stick against litres), and working out how high the fuel stands for
the picture. The chart is the oil company's table; this only stores it, checks it makes sense, and keeps the old one on record.
"""

from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from app.core.constants import Permission
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.core.tank_geometry import fill_height
from app.models.tank_dip_chart import TankDipChartPoint
from app.repositories.base import unit_of_work


class TankDipChartService:
    def __init__(self, chart_repo, tank_repo, audit_repo, auth_service):
        self._chart = chart_repo
        self._tanks = tank_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    def points(self, tank_id: str) -> List[Tuple[float, float]]:
        """(dip_cm, litres) rows of the active chart, for drawing. No permission check: it only feeds the picture."""
        return [(float(p.dip_cm), float(p.litres)) for p in self._chart.active_points(tank_id)]

    def drawing(self, tank, low_percent: float = 0.0) -> Tuple[float, str, bool, float]:
        """(height fraction, how it was worked out, whether the tank has a chart, height fraction of the low-stock line)."""
        chart = self.points(tank.id)
        height, basis = fill_height(float(tank.current_stock), float(tank.capacity), chart)
        low, _ = fill_height(float(tank.capacity) * low_percent / 100.0, float(tank.capacity), chart)
        return height, basis, len(chart) >= 2, low

    @require_permission(Permission.INVENTORY_VIEW.value)
    def get(self, actor_user_id: str, tank_id: str) -> List[TankDipChartPoint]:
        return self._chart.active_points(tank_id)

    @require_permission(Permission.INVENTORY_MANAGE.value)
    def set_chart(self, actor_user_id: str, tank_id: str, rows: List[Tuple[str, str]]) -> List[TankDipChartPoint]:
        """rows = (dip_cm, litres) as typed. The whole chart is replaced; the old rows stay on record, voided."""
        tank = self._tanks.get_by_id(tank_id)
        if tank is None:
            raise NotFoundError(f"Tank not found: {tank_id}")
        parsed: List[Tuple[Decimal, Decimal]] = []
        for dip, litres in rows:
            try:
                parsed.append((Decimal(str(dip).strip()), Decimal(str(litres).strip())))
            except InvalidOperation:
                raise ValueError(f"'{dip}' / '{litres}' are not numbers.") from None
        if len(parsed) < 2:
            raise ValueError("A dip chart needs at least two rows.")
        if any(d < 0 or l < 0 for d, l in parsed):
            raise ValueError("Dip and litres cannot be negative.")
        parsed.sort(key=lambda r: r[0])
        for (d1, l1), (d2, l2) in zip(parsed, parsed[1:]):
            if d2 == d1:
                raise ValueError(f"Dip {d1} cm appears twice.")
            if l2 < l1:
                raise ValueError(f"Litres must not fall as the dip rises: {l1} L at {d1} cm, then {l2} L at {d2} cm.")
        if parsed[-1][1] > tank.capacity * Decimal("1.05"):
            raise ValueError(f"The chart reaches {parsed[-1][1]} L but this tank holds {tank.capacity} L.")
        with unit_of_work(self._chart.session):
            voided = self._chart.void_active(tank_id)
            made = [TankDipChartPoint(tank_id=tank_id, dip_cm=d.quantize(Decimal("0.1")), litres=l.quantize(Decimal("0.001")), created_by_id=actor_user_id) for d, l in parsed]
            self._chart.add_all(made)
            self._audit_repo.record(
                event_type="tank_dip_chart_set", actor_id=actor_user_id, entity_type="Tank", entity_id=tank_id,
                description=f"{tank.code}: dip chart of {len(made)} rows entered" + (f" (replaces {voided} earlier rows, kept on record)" if voided else ""),
            )
        return made
