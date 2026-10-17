"""Checks computed from data the app already holds (shift tenders, litres, tank dips, credit).

Runners read through repositories with NO permission check on purpose: a verification must see
everything whoever happened to trigger it. Writing the verdicts goes through CheckService.record,
which is append-only and audit-logged. Report-based checks (Track 2) live in report_checks.py.
"""

from datetime import date
from decimal import Decimal
from typing import List

from app.core.constants import (
    RECONCILIATION_VARIANCE_WARNING_THRESHOLD_PERCENT,
    PaymentMethod,
    SaleStatus,
)
from app.core.money import money, volume
from app.services.check_service import CheckSpec

_Z = Decimal("0")


def link(label: str, route: str) -> dict:
    return {"label": label, "route": route}


class ExistingDataChecks:
    def __init__(self, check_service, settings, shift_repo, assignment_repo, sale_repo, shift_recon_repo,
                 fuel_recon_repo, tank_repo, credit_account_repo, payment_repo):
        self._checks = check_service
        self._settings = settings
        self._shifts = shift_repo
        self._assignments = assignment_repo
        self._sales = sale_repo
        self._shift_recon = shift_recon_repo
        self._fuel_recon = fuel_recon_repo
        self._tanks = tank_repo
        self._accounts = credit_account_repo
        self._payments = payment_repo

    def run_day(self, actor_id, day: date) -> list:
        results = []
        for spec in self.specs_for_day(day):
            results.append(self._checks.record(actor_id, spec))
        return results

    def specs_for_day(self, day: date) -> List[CheckSpec]:
        specs: List[CheckSpec] = []
        for shift in sorted(self._shifts.list_for_date_range(day, day), key=lambda s: s.created_at):
            specs += self._shift_specs(shift, day)
        specs += self._tank_specs(day)
        specs += self._credit_specs(day)
        return specs

    # -- shifts ----------------------------------------------------------------------------------------
    def _shift_specs(self, shift, day) -> List[CheckSpec]:
        name = f"{shift.shift_label} shift"
        out: List[CheckSpec] = []
        links = [link(f"Open {name}", f"/shifts/{shift.id}")]

        assignments = [a for a in self._assignments.list_for_shift(shift.id) if a.closing_meter is not None]
        if assignments:
            metered = sum(
                (a.closing_meter - a.opening_meter - a.testing_volume - a.internal_consumption_volume for a in assignments),
                _Z,
            )
            sold = sum((s.quantity for s in self._sales.list_by_shift(shift.id) if s.status == SaleStatus.COMPLETED.value), _Z)
            out.append(CheckSpec(
                key="shift.litres_match_meters", scope_type="shift", scope_id=shift.id, business_date=day, area="Stock",
                sentence=f"{name}: litres billed equal litres through the meters (less testing)",
                expected=volume(metered), actual=volume(sold), unit="litres", links=links,
            ))

        recon = self._shift_recon.get_by_shift_id(shift.id)
        if recon is not None:
            expected = sum((ln.expected for ln in recon.lines), _Z)
            declared = sum((ln.declared for ln in recon.lines), _Z)
            warn = money(abs(expected) * Decimal(str(RECONCILIATION_VARIANCE_WARNING_THRESHOLD_PERCENT)) / Decimal("100"))
            out.append(CheckSpec(
                key="shift.declared_matches_expected", scope_type="shift", scope_id=shift.id, business_date=day,
                area="Cash", sentence=f"{name}: payment totals declared equal what the sales say",
                expected=money(expected), actual=money(declared), warn_within=warn,
                links=links + [link("Reconciliation", "/reconciliation")],
            ))
        return out

    # -- tanks -----------------------------------------------------------------------------------------
    def _tank_specs(self, day) -> List[CheckSpec]:
        tolerance = self._settings.get_decimal("dip_tolerance_percent")
        out: List[CheckSpec] = []
        for tank in self._tanks.list_all():
            rows = [r for r in self._fuel_recon.list_for_tank(tank.id) if r.reconciliation_date == day]
            if not rows:
                continue
            rec = rows[0]  # newest first (repo orders by date only; one per day is the norm)
            label = tank.code or tank.name or "Tank"
            warn = volume(abs(rec.expected_closing_stock) * tolerance / Decimal("100"))
            out.append(CheckSpec(
                key="tank.dip_matches_book", scope_type="tank", scope_id=tank.id, business_date=day, area="Stock",
                sentence=f"{label}: dip reading matches the book stock",
                expected=volume(rec.expected_closing_stock), actual=volume(rec.physical_stock), unit="litres",
                warn_within=warn, links=[link(f"Open {label}", f"/tanks/{tank.id}")],
            ))
        return out

    # -- credit ----------------------------------------------------------------------------------------
    def _credit_specs(self, day) -> List[CheckSpec]:
        out: List[CheckSpec] = []
        for account in self._accounts.list_all():
            cid = account.customer_id
            name = account.customer.name if account.customer else "Customer"
            bills = sum(
                (s.amount for s in self._sales.list_by_customer(cid)
                 if s.payment_method == PaymentMethod.CREDIT.value and s.status == SaleStatus.COMPLETED.value),
                _Z,
            )
            paid = sum((p.amount for p in self._payments.list_for_customer(cid)), _Z)
            outstanding = bills - paid
            links = [link(f"Open {name}", f"/credit?customer={cid}")]
            out.append(CheckSpec(
                key="customer.within_credit_limit", scope_type="customer", scope_id=cid, business_date=day,
                area="Credit", sentence=f"{name}: outstanding is within the credit limit",
                expected=money(account.credit_limit), actual=money(outstanding), rule="at_most", links=links,
            ))
        return out
