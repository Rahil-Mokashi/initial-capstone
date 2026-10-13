"""Bank checks the owners can see: "Paytm for 12 Oct: expected 4,14,760, received ..., status".

For every payment mode that had takings on a day: what the books say should reach the bank against what the
bank statement shows. A shortfall explained by recorded bank charges is a pass; money still on its way (inside
the date window) is a warning; money past the window that never arrived is a failure. Statements with missing
rows, and bank credits nobody has accounted for, are shown the same way.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import List

from app.core.money import money
from app.services.bank_recon_service import MODE_LABELS
from app.services.check_service import CheckSpec
from app.services.daily_report_html import inr

_Z = Decimal("0")


def _link(label: str, route: str) -> dict:
    return {"label": label, "route": route}


class BankChecks:
    def __init__(self, recon, repo, check_service, settings):
        self._recon = recon
        self._repo = repo
        self._checks = check_service
        self._settings = settings

    def run_day(self, actor_id, day: date) -> list:
        return [self._checks.record(actor_id, s) for s in self.specs_for_day(actor_id, day)]

    def specs_for_day(self, actor_id, day: date) -> List[CheckSpec]:
        # keep the recent past in step with the books too: a salary or deposit is often recorded days after its date
        self._recon.sync_expected_internal(actor_id, day - timedelta(days=35), day)
        specs: List[CheckSpec] = []
        link = [_link("Open bank matching", f"/bank?date_from={day.isoformat()}&date_to={day.isoformat()}")]
        for cell in self._recon.build_days(day, day):
            pending = cell.suggested + cell.unmatched
            unresolved_ok = cell.awaiting or (cell.suggested > 0 and cell.unmatched == 0)
            note = ""
            if cell.charges:
                note += f", bank charges {inr(cell.charges)}"
            if cell.unmatched and cell.awaiting:
                note += f", {inr(cell.unmatched)} not yet seen on the statement"
            elif cell.unmatched:
                note += f", {inr(cell.unmatched)} never reached the bank"
            if cell.suggested:
                note += f", {inr(cell.suggested)} waiting for someone to confirm the match"
            specs.append(CheckSpec(
                key="bank.mode_expected_vs_received", scope_type="bank_account", scope_id=f"{day.isoformat()}:{cell.mode}",
                business_date=day, area="Bank",
                sentence=f"{cell.label} for {day:%d %b}: expected {inr(cell.expected)}, received {inr(cell.received)}{note}",
                expected=cell.expected, actual=cell.received, pass_within=cell.charges,
                warn_within=cell.charges + (pending if unresolved_ok else _Z), links=link,
            ))
        window = int(self._settings.get_decimal("bank_date_window_days"))
        today = date.today()
        claimed = self._repo.claimed_ids(("confirmed", "suggested"))[1]
        for acct in self._repo.list_accounts():
            for imp in self._repo.imports_for_account(acct.id):
                if imp.date_from and imp.date_to and imp.date_from <= day <= imp.date_to:
                    specs.append(CheckSpec(
                        key="bank.statement_has_no_missing_rows", scope_type="bank_account", scope_id=f"{acct.id}:{imp.id}",
                        business_date=day, area="Bank", unit="count",
                        sentence=f"{acct.name} statement {imp.date_from:%d %b} to {imp.date_to:%d %b}: the running balance has no gaps (no missing rows)",
                        expected=_Z, actual=Decimal(imp.break_count), links=[_link("Open bank matching", "/bank")],
                    ))
            credits = [r for r in self._repo.rows_between(day, day, acct.id) if r.credit > 0 and r.id not in claimed]
            if credits or self._repo.rows_between(day, day, acct.id):
                late = (today - day).days > window
                specs.append(CheckSpec(
                    key="bank.credits_accounted_for", scope_type="bank_account", scope_id=f"{acct.id}:{day.isoformat()}",
                    business_date=day, area="Bank", unit="count",
                    sentence=f"{acct.name}, {day:%d %b}: every bank credit is matched, or marked as not the pump's",
                    expected=_Z, actual=Decimal(len(credits)), warn_within=Decimal("0") if late else Decimal("100000"), links=link,
                ))
        return specs
