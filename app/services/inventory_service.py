"""
Service layer for petrol pump operations
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.repositories.fuel_repository import FuelRepository


class InventoryService:
    """Service level interface for fuel inventory operations"""

    def __init__(self, repo: FuelRepository):
        self._repo = repo

    def get_available_fuel(self) -> List[dict]:
        """Get all fuel types available for selling"""
        return [
            {
                "id": fuel.id,
                "type": fuel.fuel_type,
                "rate": fuel.rate_per_liter,
                "capacity": fuel.capacity,
                "opening_stock": fuel.opening_stock,
            }
            for fuel in self._repo.list_active()
        ]

    def update_fuel_capacity(self, fuel_id: str, quantity: float) -> Optional[dict]:
        """Update fuel capacity after sale"""
        fuel = self._repo.get_by_id(fuel_id)
        if fuel and fuel.is_active and quantity <= fuel.current_stock:
            fuel.current_stock -= quantity
            fuel.updated_at = datetime.now(timezone.utc)
            self._repo.update(fuel)
            return {
                "id": fuel.id,
                "type": fuel.fuel_type,
                "updated_quantity": quantity,
                "new_stock": fuel.current_stock,
            }
        return None