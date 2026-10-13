"""The salary tallies the owners used to trust the Excel for, shown as checks that pass or fail.

Per employee: gross - deductions = net. Per month: the register total equals the lines, equals what was paid; every
payment was made after an owner approved the month; bank payments appear among the bank's expected debits; and
advances recovered never exceed advances given (given = recovered + still outstanding, with nothing negative).
"""

from datetime import date
from decimal import Decimal
from typing import List

from app.core.money import money
from app.services.check_service import CheckSpec
from app.services.payroll_service import month_bounds

_Z = Decimal("0")


def _link(label: str, route: str) -> dict:
    return {"label": label, "route": route}


class PayrollChecks:
    def __init__(self, payroll, repo, check_service, bank_repo=None):
        self._payroll = payroll
        self._repo = repo
        self._checks = check_service
        self._bank = bank_repo

    def run_day(self, actor_id, day: date) -> list:
        out = []
        prev = (day.replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%Y-%m")  # last month is paid in this one
        for month in (day.strftime("%Y-%m"), prev):
            out += [self._checks.record(actor_id, s) for s in self.specs_for_month(month, day)]
        return out

    def specs_for_month(self, month: str, day: date) -> List[CheckSpec]:
        reg = self._payroll.register_internal(month)
        if reg is None:
            return []
        link = [_link(f"Open payroll {month}", f"/payroll?month={month}")]
        specs: List[CheckSpec] = []
        for lv in reg.lines:
            l = lv.line
            specs.append(CheckSpec(
                key="payroll.line_net_adds_up", scope_type="payroll_month", scope_id=f"{month}:{l.employee_id}", business_date=day,
                area="Payroll", sentence=f"{l.employee_name}, {month}: salary earned minus deductions equals the net pay",
                expected=money(l.gross - l.advance_deduction - l.shortage_deduction - l.other_deduction), actual=money(l.net), links=link,
            ))
            specs.append(CheckSpec(
                key="payroll.days_within_month", scope_type="payroll_month", scope_id=f"{month}:{l.employee_id}:days", business_date=day,
                area="Payroll", unit="count", sentence=f"{l.employee_name}, {month}: days paid for are not more than the days in the month",
                expected=Decimal(l.days_in_month), actual=l.paid_days, rule="at_most", links=link,
            ))
            given = self._payroll.advance_given(l.employee_id, month_bounds(month)[1])
            recovered = self._payroll.advance_recovered(l.employee_id)
            specs.append(CheckSpec(
                key="payroll.advances_recovered_not_more_than_given", scope_type="payroll_month", scope_id=f"{month}:{l.employee_id}:advances",
                business_date=day, area="Payroll",
                sentence=f"{l.employee_name}: advances given {given}, recovered {recovered}, still outstanding {money(given - recovered)}",
                expected=money(given), actual=money(recovered), rule="at_most", links=link,
            ))
        lines_total = sum((lv.line.net for lv in reg.lines), _Z)
        specs.append(CheckSpec(
            key="payroll.register_total_equals_lines", scope_type="payroll_month", scope_id=month, business_date=day, area="Payroll",
            sentence=f"{month}: the register total equals the sum of every employee's net pay",
            expected=money(lines_total), actual=money(reg.net), links=link,
        ))
        paid_lines = [lv for lv in reg.lines if lv.payment is not None]
        if paid_lines:
            specs.append(CheckSpec(
                key="payroll.payments_equal_register", scope_type="payroll_month", scope_id=f"{month}:paid", business_date=day, area="Payroll",
                sentence=f"{month}: money paid out equals the net pay of those marked paid",
                expected=money(sum((lv.line.net for lv in paid_lines), _Z)), actual=money(reg.paid), links=link,
            ))
            specs.append(CheckSpec(
                key="payroll.paid_only_after_approval", scope_type="payroll_month", scope_id=f"{month}:approval", business_date=day,
                area="Payroll", unit="count", sentence=f"{month}: every payment was made after an owner approved the month",
                expected=_Z, actual=Decimal(0 if reg.run.status in ("approved", "paid") and reg.run.approved_by_id else len(paid_lines)),
                links=link,
            ))
        if self._bank is not None:
            bank_pays = [lv for lv in paid_lines if lv.payment.method == "bank"]
            if bank_pays:
                keys = {f"payroll:{lv.payment.id}" for lv in bank_pays}
                have = {e.source_key for e in self._bank.active_expected_with_keys("payroll:")}
                missing = len(keys - have)
                specs.append(CheckSpec(
                    key="payroll.bank_payments_in_bank_view", scope_type="payroll_month", scope_id=f"{month}:bank", business_date=day,
                    area="Payroll", unit="count",
                    sentence=f"{month}: every salary paid from the bank appears among the bank's expected payments",
                    expected=_Z, actual=Decimal(missing), links=[_link("Open bank matching", "/bank")],
                ))
        return specs
