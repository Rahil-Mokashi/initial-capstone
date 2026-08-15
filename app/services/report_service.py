"""
Reporting service layer (problemstatement.md #25-32, Phase 16).

This is a first, narrowly-scoped slice: an inventory summary sectioned by
fuel type (Petrol/Diesel/Power, or whatever fuel types exist), per the
user's explicit request that fuel data be reported per fuel type rather
than as one aggregate. It draws on Tank/Nozzle data that already exists
(both carry fuel_id). The full Phase 16 scope — daily/shift/attendant/HR/
financial/management reports with PDF/Excel export and print preview — is
much larger and deliberately not attempted here.
"""

from dataclasses import dataclass
from typing import List, Optional

from app.core.constants import Permission
from app.core.permissions import require_permission


@dataclass
class FuelTypeSummary:
    fuel_type: str
    fuel_id: str
    tank_count: int = 0
    total_capacity: float = 0.0
    total_current_stock: float = 0.0
    nozzle_count: int = 0
    active_nozzle_count: int = 0
    latest_variance_percent: Optional[float] = None
    latest_variance_classification: Optional[str] = None


class ReportService:
    def __init__(self, fuel_repo, tank_repo, nozzle_repo, reconciliation_repo, auth_service):
        self._fuel_repo = fuel_repo
        self._tank_repo = tank_repo
        self._nozzle_repo = nozzle_repo
        self._reconciliation_repo = reconciliation_repo
        self._auth_service = auth_service

    @require_permission(Permission.INVENTORY_VIEW.value)
    def get_fuel_type_summary(self, actor_user_id: str) -> List[FuelTypeSummary]:
        fuels = self._fuel_repo.list_active()
        tanks = self._tank_repo.list_all()
        nozzles = self._nozzle_repo.list_all()

        summaries = []
        for fuel in fuels:
            fuel_tanks = [t for t in tanks if t.fuel_id == fuel.id]
            fuel_nozzles = [n for n in nozzles if n.fuel_id == fuel.id]

            summary = FuelTypeSummary(
                fuel_type=fuel.fuel_type,
                fuel_id=fuel.id,
                tank_count=len(fuel_tanks),
                total_capacity=sum(t.capacity for t in fuel_tanks),
                total_current_stock=sum(t.current_stock for t in fuel_tanks),
                nozzle_count=len(fuel_nozzles),
                active_nozzle_count=len([n for n in fuel_nozzles if n.status == "active"]),
            )

            latest_variances = []
            for tank in fuel_tanks:
                latest = self._reconciliation_repo.get_latest_for_tank(tank.id)
                if latest:
                    latest_variances.append(latest)
            if latest_variances:
                worst = max(latest_variances, key=lambda r: abs(r.variance_percent))
                summary.latest_variance_percent = worst.variance_percent
                summary.latest_variance_classification = worst.classification

            summaries.append(summary)

        return summaries
