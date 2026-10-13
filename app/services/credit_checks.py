"""Credit checks the owners can see: bills add up per shift, balances add up per customer, and no bill went past
the limit unless an owner's override is on record.

Each compares figures reached by different routes (per shift vs per customer; the payment-application
arithmetic vs the plain totals), so a bad record, a credit sale with no customer, or a limit that was
passed without an owner's say-so shows up as a failure rather than a surprise at month end.
"""

from datetime import date
from decimal import Decimal
from typing import List

from app.core.constants import PaymentMethod, SaleStatus
from app.core.money import money
from app.services.check_service import CheckSpec
from app.services.customer_ledger import apply_payments

_Z = Decimal("0")


def _link(label: str, route: str) -> dict:
    return {"label": label, "route": route}


class CreditChecks:
    def __init__(self, ledger, control, check_service, sale_repo, shift_repo, account_repo):
        self._ledger = ledger
        self._control = control
        self._checks = check_service
        self._sales = sale_repo
        self._shifts = shift_repo
        self._accounts = account_repo

    def run_day(self, actor_id, day: date) -> list:
        return [self._checks.record(actor_id, s) for s in self.specs_for_day(day)]

    def specs_for_day(self, day: date) -> List[CheckSpec]:
        specs: List[CheckSpec] = []
        accounts = list(self._accounts.list_all())
        data = {a.customer_id: self._ledger.bills_and_payments(a.customer_id) for a in accounts}

        # 1. credit sale totals = the sum of the customers' bills, per shift
        for shift in self._shifts.list_for_date_range(day, day):
            on_shift = sum(
                (s.amount for s in self._sales.list_by_shift(shift.id)
                 if s.payment_method == PaymentMethod.CREDIT.value and s.status == SaleStatus.COMPLETED.value),
                _Z,
            )
            per_customer = sum(
                (b.amount for bills, _ in data.values() for b in bills if b.kind == "sale" and b.shift_id == shift.id), _Z
            )
            specs.append(CheckSpec(
                key="credit.shift_credit_equals_customer_bills", scope_type="shift", scope_id=shift.id, business_date=day,
                area="Credit", sentence=f"{shift.shift_label} shift: credit sales equal the bills on the customers' accounts",
                expected=money(on_shift), actual=money(per_customer), links=[_link("Open Credit", "/credit")],
            ))

        override_ids = self._control.override_sale_ids()
        for a in accounts:
            bills, pays = data[a.customer_id]
            if not bills and not pays:
                continue
            name = a.customer.name if a.customer else "Customer"
            link = [_link(f"Open {name}", f"/credit/customers/{a.customer_id}")]
            # 2. balance = bills - payments, against the oldest-first application of payments
            summary = apply_payments([_copy(b) for b in bills], pays, day)
            plain = sum((b.amount for b in bills), _Z) - sum((p.amount for p in pays), _Z)
            applied = sum((b.outstanding for b in summary.bills), _Z) - summary.unapplied
            specs.append(CheckSpec(
                key="credit.balance_is_bills_minus_payments", scope_type="customer", scope_id=a.customer_id, business_date=day,
                area="Credit", sentence=f"{name}: balance equals bills minus payments (and every payment is accounted for)",
                expected=money(plain), actual=money(applied), links=link,
            ))
            # 3. no bill of the day takes the customer past the limit without an owner's override on record
            events = sorted(
                [(b.bill_date, 0, b.order, b) for b in bills] + [(p.pay_date, 1, 0, p) for p in pays], key=lambda e: e[:3]
            )
            level = _Z
            for when, _, _, item in events:
                level += item.amount if hasattr(item, "kind") else -item.amount
                if hasattr(item, "kind") and item.kind == "sale" and when == day:
                    overridden = item.sale_id in override_ids
                    over = level > a.credit_limit
                    specs.append(CheckSpec(
                        key="credit.bill_within_limit_or_overridden", scope_type="bill", scope_id=item.sale_id, business_date=day,
                        area="Credit",
                        sentence=(f"{name}, bill {item.ref}: within the credit limit"
                                  + (" (past it, but an owner allowed it)" if over and overridden else "")),
                        expected=money(a.credit_limit), actual=money(a.credit_limit if overridden else level), rule="at_most",
                        links=link,
                    ))
        return specs


def _copy(b):
    from dataclasses import replace

    return replace(b)
