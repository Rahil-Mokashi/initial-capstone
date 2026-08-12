"""
Service layer for petrol pump operations
"""

from datetime import datetime
from typing import List, Optional
from ..database.models.base import QueryFilterBase
from ..database.repository import Repository


class InventoryService(QueryFilterBase):
    """Service level interface for fuel inventory operations"""

    def __init__(self, repo: Repository):
        self._repo = repo

    def _apply_filter(self, query, filters: dict) -> Query:
        """Apply business logic filters"""
        query = super()._apply_filter(query, filters)

        # Add default filters
        if "status" in filters and not filters["status"]:
            query = query.filter_by(status="active")
        return query

    def get_available_fuel(self) -> List[dict]:
        """Get all fuel types available for selling"""
        return [
            {
                "id": fuel.id,
                "type": fuel.fuel_type,
                "rate": fuel.rate_per_liter,
                "capacity": fuel.capacity,
                "opening_stock": fuel.opening_stock
            }
            for fuel in self._repo.get_all_fuel()
            if fuel.is_active
        ]

    def update_fuel_capacity(self, fuel_id: int, quantity: float) -> Optional[dict]:
        """Update fuel capacity after sale"""
        fuel = self._repo.get_by_id(fuel_id)
        if fuel and fuel.is_active and quantity <= fuel.current_stock:
            fuel.current_stock -= quantity
            fuel.last_updated = datetime.utcnow()
            self._repo.update(fuel)
            return {
                "id": fuel.id,
                "type": fuel.fuel_type,
                "updated_quantity": quantity,
                "new_stock": fuel.current_stock
            }
        return None

    def generate_report(self, period: str) -> dict:
        """Generate aggregation report for given period"""
        # Filter by date range
        from_date = datetime.now().replace(day=1)
        to_date = datetime.now().replace(day=1)  # Simplified for example

        results = self._repo.execute_query(
            """SELECT fuel_type, SUM(amount) as total_sales
             FROM sales
             WHERE sale_date BETWEEN :from_date AND :to_date
             GROUP BY fuel_type""",
            {"from_date": date(from_date.year, from_date.month, 1),
             "to_date": to_date}
        )

        return {
            "period": period,
            "summary": dict(results) if results else {}
        }


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