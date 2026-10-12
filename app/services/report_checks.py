"""One check per formula on the owner's daily report, so the owners SEE each one pass or fail.

Some of these compare two figures that come from different places in the data (the report formula vs
the tank's own book, the shift total vs what the payment modes add up to, the bowser meter vs its
bills). Others re-add what the report already adds; they are cheap guards that fail loudly if a future
change or a bad record ever makes the printed figures disagree with the records behind them.
"""

from datetime import date
from decimal import Decimal
from typing import List

from app.core.money import money, volume
from app.services.check_service import CheckSpec

_Z = Decimal("0")
ONE_PAISA = Decimal("0.01")


def _link(label: str, route: str) -> dict:
    return {"label": label, "route": route}


class ReportChecks:
    def __init__(self, check_service, report_service, settings):
        self._checks = check_service
        self._report = report_service
        self._settings = settings

    def run_day(self, actor_id, day: date) -> list:
        return [self._checks.record(actor_id, s) for s in self.specs_for_day(actor_id, day)]

    def specs_for_day(self, actor_id, day: date) -> List[CheckSpec]:
        r = self._report.compute(day, actor_id)
        real_shifts = [s for s in r.shifts if s.shift_id]
        if not real_shifts:
            return []  # nothing happened on this day: nothing to verify
        specs: List[CheckSpec] = []
        day_id = day.isoformat()
        report_link = [_link("Open the daily report", f"/daily-report?day={day_id}")]
        tolerance = self._settings.get_decimal("dip_tolerance_percent")

        for col in r.tanks:
            sold = sum((s.litres_by_tank.get(col.tank_id, _Z) for s in r.shifts), _Z)
            by_formula = r.opening[col.tank_id] + r.purchase[col.tank_id] - sold
            tank_link = [_link(f"Open {col.code}", f"/tanks/{col.tank_id}")]
            specs.append(CheckSpec(
                key="report.tank_stock_matches_book", scope_type="tank", scope_id=f"{day_id}:{col.tank_id}",
                business_date=day, area="Stock", unit="litres",
                sentence=f"{col.code}: O/S + Purchase - Shift1 - Shift2 equals the tank's own book",
                expected=volume(by_formula), actual=r.tank_book_end[col.tank_id], links=tank_link + report_link,
            ))
            dip = r.closing.get(col.tank_id)
            if dip is not None:
                stock = r.total_stock[col.tank_id]
                specs.append(CheckSpec(
                    key="report.dip_matches_total_stock", scope_type="tank", scope_id=f"{day_id}:{col.tank_id}",
                    business_date=day, area="Stock", unit="litres",
                    sentence=f"{col.code}: closing dip matches Total Stock (within {tolerance}%)",
                    expected=stock, actual=dip, warn_within=volume(abs(stock) * tolerance / Decimal("100")),
                    links=tank_link + report_link,
                ))
        unassigned = sum((s.unassigned_litres for s in r.shifts), _Z)
        specs.append(CheckSpec(
            key="report.every_litre_has_a_tank", scope_type="day", scope_id=day_id, business_date=day, area="Stock",
            unit="litres", sentence="Every litre sold is on a nozzle that belongs to a tank",
            expected=_Z, actual=volume(unassigned), links=report_link,
        ))

        for s in real_shifts:
            shift_link = [_link(f"Open Shift {s.number}", f"/shifts/{s.shift_id}")] + report_link
            sid = s.shift_id
            specs.append(CheckSpec(
                key="report.shift_total_equals_total_sale", scope_type="shift", scope_id=sid, business_date=day,
                area="Daily report", sentence=f"Shift {s.number}: payment modes, expenses, Advance and Final add up to the shift's Total Sale",
                expected=s.total_sale, actual=s.lines_total, links=shift_link,
            ))
            specs.append(CheckSpec(
                key="report.shift_credit_matches_credit_mode", scope_type="shift", scope_id=sid, business_date=day,
                area="Credit", sentence=f"Shift {s.number}: credit bills listed equal the credit payment mode",
                expected=s.credit_total, actual=money(s.credit_by_tender_rs), links=shift_link,
            ))
            specs.append(CheckSpec(
                key="report.shift_cash_book_balances", scope_type="shift", scope_id=sid, business_date=day, area="Cash",
                sentence=f"Shift {s.number}: cash book receipts equal payments", expected=s.receipts_total,
                actual=s.payments_total, links=shift_link,
            ))
            specs.append(CheckSpec(
                key="report.shift_cash_in_hand_not_negative", scope_type="shift", scope_id=sid, business_date=day,
                area="Cash", sentence=f"Shift {s.number}: cash in hand is not below zero", expected=_Z,
                actual=money(s.cash_in_hand), rule="at_least", links=shift_link,
            ))
            specs.append(CheckSpec(
                key="report.shift_expenses_approved", scope_type="shift", scope_id=sid, business_date=day,
                area="Daily report", unit="count", sentence=f"Shift {s.number}: every expense on the report has been approved",
                expected=_Z, actual=Decimal(s.pending_expenses), warn_within=Decimal("100000"),
                links=[_link("Open Expenses", "/expenses")] + report_link,
            ))
            oil = [o for o in r.oil_rows if o.shift_label == f"Shift {s.number}"]
            again = money(sum((o.sale * o.rate for o in oil), _Z)) if r.rounding_rule == "per_total" else sum(
                (money(o.sale * o.rate) for o in oil), _Z)
            specs.append(CheckSpec(
                key="report.shift_oil_equals_oil_sale", scope_type="shift", scope_id=sid, business_date=day,
                area="Daily report", sentence=f"Shift {s.number}: Oil figure equals the sum of Sale x Rate on the Oil sale table",
                expected=s.oil_rs, actual=money(again), links=[_link("Open Lubricants", "/lubricants")] + report_link,
            ))

        with_books = [s for s in real_shifts if s.has_cash_book]
        for a, b in zip(with_books, with_books[1:]):
            specs.append(CheckSpec(
                key="report.next_opening_is_previous_cash_in_hand", scope_type="day", scope_id=f"{day_id}:cash{b.number}",
                business_date=day, area="Cash",
                sentence=f"Shift {b.number}'s Opening Balance equals Shift {a.number}'s Cash in hand",
                expected=money(a.cash_in_hand), actual=money(b.opening_balance), links=report_link,
            ))

        fuel_rs = sum((s.fuel_rs for s in r.shifts), _Z)
        specs.append(CheckSpec(
            key="report.day_fuel_only_total", scope_type="day", scope_id=day_id, business_date=day, area="Daily report",
            sentence="Total Rs (shift Total Sale less Oil) equals the fuel rupees of the day's sales",
            expected=money(fuel_rs), actual=r.total_rs, links=report_link,
        ))

        counts = {}
        for o in r.oil_rows:
            counts[o.item_id] = (o.name, o.balance)
        for item_id, (name, bal) in counts.items():
            specs.append(CheckSpec(
                key="report.oil_stock_not_negative", scope_type="day", scope_id=f"{day_id}:oil:{item_id}",
                business_date=day, area="Stock", unit="count", sentence=f"{name}: oil stock after the day's sales is not below zero",
                expected=_Z, actual=bal, rule="at_least", links=[_link("Open Lubricants", "/lubricants")] + report_link,
            ))

        b = r.bowser
        if b is not None and (b.bills or b.meter is not None or len(b.stock_lines) > 1):
            bl = [_link("Open the bowser", f"/bowser?day={day_id}")] + report_link
            specs.append(CheckSpec(
                key="report.bowser_meter_equals_bills", scope_type="day", scope_id=f"{day_id}:bowser_meter", business_date=day,
                area="Daily report", unit="litres", sentence="Bowser: meter Net Sale (End - Start - Testing) equals the litres on the bills",
                expected=volume(b.bills_qty), actual=volume(b.meter_net) if b.meter_net is not None else None, links=bl,
            ))
            specs.append(CheckSpec(
                key="report.bowser_closing_not_negative", scope_type="day", scope_id=f"{day_id}:bowser_stock", business_date=day,
                area="Stock", unit="litres", sentence="Bowser: Closing Stock (internal stock - bills) is not below zero",
                expected=_Z, actual=volume(b.closing_litres), rule="at_least", links=bl,
            ))
            recomputed = sum((money(x.quantity * x.rate) + x.transport for x in b.bills), _Z)
            specs.append(CheckSpec(
                key="report.bowser_bill_totals", scope_type="day", scope_id=f"{day_id}:bowser_bills", business_date=day,
                area="Daily report", sentence="Bowser: each bill's Total equals Qty x rate + Transport",
                expected=money(recomputed), actual=money(b.bills_total), links=bl,
            ))
        return specs
