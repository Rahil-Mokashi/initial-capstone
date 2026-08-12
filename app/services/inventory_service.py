"""
Service layer for petrol pump operations
"""

from datetime import datetime
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
            fuel.updated_at = datetime.utcnow()
            self._repo.update(fuel)
            return {
                "id": fuel.id,
                "type": fuel.fuel_type,
                "updated_quantity": quantity,
                "new_stock": fuel.current_stock,
            }
        return None


# Single Responsibility Principle - Only handles inventory operations
class EmployeeService:
    """Service layer for employee operations"""

    def __init__(self, repo):
        self._repo = repo

    def assign_nozzle(self, employee_id: int, nozzle_id: int, shift_id: int) -> bool:
        """Validate and assign nozzle to employee"""
        # Business logic validation
        if not self._repo.get_employee_shift(employee_id, shift_id):
            return False
        if self._repo.get_nozzle_assignments(nozzle_id):
            return False
        return True


# Repository pattern separated from service layer
class PaymentRepository(Repository):
    """Data access layer for payment operations"""

    def record_payment(self, sale_id: int, amount: float, payment_method: str) -> bool:
        """Record payment with proper accounting"""
        if amount <= 0:
            return False
        return self._session.execute(
            """INSERT INTO payments
             (sale_id, amount, payment_method, created_at)
             VALUES (:sale_id, :amount, :payment_method, NOW())""",
            {"sale_id": sale_id, "amount": amount, "payment_method": payment_method}
        ).rowcount > 0