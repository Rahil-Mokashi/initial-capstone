"""
Tank & Inventory service layer (problemstatement.md #13, #14, Phase 9).

Tank.current_stock is the book value, moved only by recorded transactions
(receipts/issues/adjustments) — never by a dip reading, which is just an
observation. Reconciliation compares the book value's expected trajectory
against a physical reading, classifies the variance (never assuming
theft), and — once accepted — resets the tank's book value to the
physical figure so the next period starts from a verified baseline.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.core.constants import (
    FUEL_VARIANCE_APPROVAL_THRESHOLD_PERCENT,
    FUEL_VARIANCE_INVESTIGATION_THRESHOLD_PERCENT,
    FUEL_VARIANCE_WARNING_THRESHOLD_PERCENT,
    Permission,
    TankStatus,
    TankTransactionType,
    VarianceClassification,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.fuel_reconciliation import FuelReconciliation
from app.models.tank import Tank
from app.models.tank_reading import TankReading
from app.models.tank_transaction import TankTransaction
from app.schemas.tank import ReconciliationPerform, TankCreate, TankReadingCreate, TankTransactionCreate


def classify_variance(variance_percent: float) -> VarianceClassification:
    magnitude = abs(variance_percent)
    if magnitude <= FUEL_VARIANCE_WARNING_THRESHOLD_PERCENT:
        return VarianceClassification.NORMAL
    if magnitude <= FUEL_VARIANCE_INVESTIGATION_THRESHOLD_PERCENT:
        return VarianceClassification.WARNING
    if magnitude <= FUEL_VARIANCE_APPROVAL_THRESHOLD_PERCENT:
        return VarianceClassification.INVESTIGATION_REQUIRED
    return VarianceClassification.APPROVAL_REQUIRED


class TankService:
    def __init__(
        self,
        tank_repo,
        reading_repo,
        transaction_repo,
        reconciliation_repo,
        fuel_repo,
        employee_repo,
        audit_repo,
        auth_service,
    ):
        self._tank_repo = tank_repo
        self._reading_repo = reading_repo
        self._transaction_repo = transaction_repo
        self._reconciliation_repo = reconciliation_repo
        self._fuel_repo = fuel_repo
        self._employee_repo = employee_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    @require_permission(Permission.INVENTORY_MANAGE.value)
    def create_tank(self, actor_user_id: str, data: TankCreate) -> Tank:
        if self._tank_repo.get_by_code(data.code):
            raise ConflictError(f"A tank with code {data.code!r} already exists")
        if not self._fuel_repo.get_by_id(data.fuel_id):
            raise NotFoundError(f"Fuel type not found: {data.fuel_id}")
        if data.opening_stock > data.capacity:
            raise ConflictError("opening_stock cannot exceed capacity")

        tank = Tank(
            code=data.code,
            fuel_id=data.fuel_id,
            capacity=data.capacity,
            current_stock=data.opening_stock,
            opening_stock=data.opening_stock,
            calibration_info=data.calibration_info,
            status=TankStatus.ACTIVE.value,
        )
        tank = self._tank_repo.add(tank)
        self._audit_repo.record(
            event_type="tank_created",
            actor_id=actor_user_id,
            entity_type="Tank",
            entity_id=tank.id,
            description=f"Created tank {data.code}",
        )
        return tank

    @require_permission(Permission.INVENTORY_MANAGE.value)
    def set_tank_status(self, actor_user_id: str, tank_id: str, status: TankStatus, reason: str) -> Tank:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to change a tank's status")

        tank = self._get_tank_or_raise(tank_id)
        old_status = tank.status
        tank.status = status.value
        tank = self._tank_repo.update(tank)
        self._audit_repo.record(
            event_type="tank_status_changed",
            actor_id=actor_user_id,
            entity_type="Tank",
            entity_id=tank.id,
            description=reason.strip(),
            old_value=old_status,
            new_value=status.value,
        )
        return tank

    @require_permission(Permission.INVENTORY_VIEW.value)
    def list_tanks(self, actor_user_id: str) -> List[Tank]:
        return self._tank_repo.list_all()

    @require_permission(Permission.INVENTORY_VIEW.value)
    def get_tank(self, actor_user_id: str, tank_id: str) -> Tank:
        return self._get_tank_or_raise(tank_id)

    @require_permission(Permission.INVENTORY_MANAGE.value)
    def record_reading(self, actor_user_id: str, tank_id: str, data: TankReadingCreate) -> TankReading:
        self._get_tank_or_raise(tank_id)
        if not self._employee_repo.get_by_id(data.employee_id):
            raise NotFoundError(f"Employee not found: {data.employee_id}")

        reading = TankReading(
            tank_id=tank_id,
            employee_id=data.employee_id,
            shift_id=data.shift_id,
            dip_value=data.dip_value,
            physical_stock=data.physical_stock,
            remarks=data.remarks,
            reading_at=data.reading_at or datetime.now(timezone.utc),
        )
        reading = self._reading_repo.add(reading)
        self._audit_repo.record(
            event_type="tank_reading_recorded",
            actor_id=actor_user_id,
            entity_type="TankReading",
            entity_id=reading.id,
            description=f"Physical stock reading {data.physical_stock} for tank {tank_id}",
        )
        return reading

    @require_permission(Permission.INVENTORY_VIEW.value)
    def list_readings(self, actor_user_id: str, tank_id: str) -> List[TankReading]:
        return self._reading_repo.list_for_tank(tank_id)

    @require_permission(Permission.INVENTORY_MANAGE.value)
    def record_transaction(
        self, actor_user_id: str, tank_id: str, transaction_type: TankTransactionType, data: TankTransactionCreate
    ) -> TankTransaction:
        tank = self._get_tank_or_raise(tank_id)

        if transaction_type in (TankTransactionType.RECEIPT, TankTransactionType.ISSUE) and data.quantity <= 0:
            raise ValueError(f"{transaction_type.value} quantity must be positive")
        if transaction_type == TankTransactionType.ADJUSTMENT and (not data.remarks or not data.remarks.strip()):
            raise ValueError("A reason is required to record a stock adjustment")

        if transaction_type == TankTransactionType.RECEIPT:
            new_stock = tank.current_stock + data.quantity
            if new_stock > tank.capacity:
                raise ConflictError(
                    f"Receiving {data.quantity} would exceed tank capacity ({tank.capacity}); "
                    f"current stock is {tank.current_stock}"
                )
        elif transaction_type == TankTransactionType.ISSUE:
            new_stock = tank.current_stock - data.quantity
            if new_stock < 0:
                raise ConflictError(
                    f"Cannot issue {data.quantity}; only {tank.current_stock} is currently in stock"
                )
        else:
            new_stock = tank.current_stock + data.quantity
            if new_stock < 0:
                raise ConflictError("This adjustment would make the tank's stock negative")
            if new_stock > tank.capacity:
                raise ConflictError("This adjustment would exceed the tank's capacity")

        stored_quantity = data.quantity if transaction_type != TankTransactionType.ISSUE else -data.quantity
        transaction = TankTransaction(
            tank_id=tank_id,
            transaction_type=transaction_type.value,
            quantity=stored_quantity,
            recorded_by_id=actor_user_id,
            reference=data.reference,
            remarks=data.remarks,
        )
        transaction = self._transaction_repo.add(transaction)

        tank.current_stock = new_stock
        self._tank_repo.update(tank)

        self._audit_repo.record(
            event_type="tank_transaction_recorded",
            actor_id=actor_user_id,
            entity_type="TankTransaction",
            entity_id=transaction.id,
            description=f"{transaction_type.value} of {data.quantity} on tank {tank.code}; new stock {new_stock}",
        )
        return transaction

    @require_permission(Permission.INVENTORY_VIEW.value)
    def list_transactions(self, actor_user_id: str, tank_id: str) -> List[TankTransaction]:
        return self._transaction_repo.list_for_tank(tank_id)

    @require_permission(Permission.INVENTORY_MANAGE.value)
    def perform_reconciliation(self, actor_user_id: str, tank_id: str, data: ReconciliationPerform) -> FuelReconciliation:
        tank = self._get_tank_or_raise(tank_id)

        last_reconciliation = self._reconciliation_repo.get_latest_for_tank(tank_id)
        period_start = last_reconciliation.reconciliation_date if last_reconciliation else None
        opening_stock = last_reconciliation.physical_stock if last_reconciliation else tank.opening_stock

        received = self._transaction_repo.sum_for_tank_by_type(
            tank_id, TankTransactionType.RECEIPT.value, date_from=period_start, date_to=data.reconciliation_date
        )
        issued = abs(
            self._transaction_repo.sum_for_tank_by_type(
                tank_id, TankTransactionType.ISSUE.value, date_from=period_start, date_to=data.reconciliation_date
            )
        )

        expected_closing_stock = opening_stock + received - issued
        variance = data.physical_stock - expected_closing_stock
        variance_percent = (
            (variance / expected_closing_stock) * 100 if expected_closing_stock != 0 else (0.0 if variance == 0 else 100.0)
        )
        classification = classify_variance(variance_percent)

        reconciliation = FuelReconciliation(
            tank_id=tank_id,
            reconciliation_date=data.reconciliation_date,
            opening_stock=opening_stock,
            received_quantity=received,
            sold_quantity=issued,
            expected_closing_stock=expected_closing_stock,
            physical_stock=data.physical_stock,
            variance=variance,
            variance_percent=variance_percent,
            classification=classification.value,
            performed_by_id=actor_user_id,
            remarks=data.remarks,
        )
        reconciliation = self._reconciliation_repo.add(reconciliation)

        old_stock = tank.current_stock
        tank.current_stock = data.physical_stock
        tank.opening_stock = data.physical_stock
        self._tank_repo.update(tank)

        self._audit_repo.record(
            event_type="fuel_reconciliation_performed",
            actor_id=actor_user_id,
            entity_type="FuelReconciliation",
            entity_id=reconciliation.id,
            description=(
                f"Reconciled tank {tank.code}: expected {expected_closing_stock:.2f}, "
                f"physical {data.physical_stock:.2f}, variance {variance:.2f} ({classification.value})"
            ),
            old_value=str(old_stock),
            new_value=str(data.physical_stock),
        )
        return reconciliation

    @require_permission(Permission.INVENTORY_VIEW.value)
    def list_reconciliations(self, actor_user_id: str, tank_id: str) -> List[FuelReconciliation]:
        return self._reconciliation_repo.list_for_tank(tank_id)

    def _get_tank_or_raise(self, tank_id: str) -> Tank:
        tank = self._tank_repo.get_by_id(tank_id)
        if not tank:
            raise NotFoundError(f"Tank not found: {tank_id}")
        return tank
