"""The Plus daily report: the Classic report in the same order, plus what the owners asked to SEE.

A checks strip at the top, bank status beside each payment mode, the rupee sign and fixed decimals, the dip difference per
tank as a percentage against the tolerance (T-02), the bowser meter against its bills as a pass/fail line, the day's credit,
and prepared-by / checked-by lines with a page footer and a short hash of the report contents. Finalising a day stores
that hash and writes it to the audit log, so a later change to the figures is visible.
"""

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from html import escape
from typing import Optional

from app.core.constants import Permission
from app.core.permissions import require_permission
from app.models.daily_report_final import DailyReportFinal
from app.services.daily_report_html import _STYLE, inr, litres
from app.services.daily_report_service import DailyReport, report_to_dict
from app.services.tender_entry_service import REPORT_LABELS

_Z = Decimal("0")


def content_hash(report: DailyReport) -> str:
    """Short fingerprint of everything the report prints; changes whenever a figure behind it changes."""
    blob = json.dumps(report_to_dict(report), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def _e(t) -> str:
    return escape(str(t if t is not None else ""))


class ReportFinaliser:
    def __init__(self, session, report_service, audit_repo, auth_service):
        self._session = session
        self._report = report_service
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    def latest(self, day: date) -> Optional[DailyReportFinal]:
        return (
            self._session.query(DailyReportFinal).filter_by(report_date=day)
            .order_by(DailyReportFinal.finalised_at.desc()).first()
        )

    @require_permission(Permission.DAILY_REPORT_FINALISE.value)
    def finalise(self, actor_user_id: str, day: date, style: str) -> DailyReportFinal:
        report = self._report.compute(day, actor_user_id)
        h = content_hash(report)
        row = DailyReportFinal(report_date=day, style=style, content_hash=h, finalised_by_id=actor_user_id)
        self._session.add(row)
        self._session.flush()
        self._audit_repo.record(
            event_type="daily_report_finalised", actor_id=actor_user_id, entity_type="DailyReportFinal", entity_id=row.id,
            description=f"Daily report for {day} ({style}) finalised; contents hash {h}", new_value=h,
        )
        self._session.commit()
        self._session.refresh(row)
        return row


def build_extras(services, report: DailyReport, actor_id: str) -> dict:
    token = _STYLE.set("plus")  # the extras use the same rupee sign and two-place litres as the page
    try:
        return _build(services, report, actor_id)
    finally:
        _STYLE.reset(token)


def _build(services, report: DailyReport, actor_id: str) -> dict:
    day = report.day
    user = services.user_repo.get_by_id(actor_id)
    who = (f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username) if user else ""
    h = content_hash(report)
    final = services.report_finaliser.latest(day)

    rows = services.checks._results.current_for_day(day)
    bad = [r for r in rows if r.status == "fail"]
    passed = sum(1 for r in rows if r.status == "pass")
    if not rows:
        strip = '<div class="strip">No checks have run for this day yet.</div>'
    elif not bad:
        strip = f'<div class="strip">{passed} of {len(rows)} checks passed</div>'
    else:
        names = "; ".join(_e(r.sentence) for r in bad[:4]) + (f" and {len(bad) - 4} more" if len(bad) > 4 else "")
        strip = f'<div class="strip bad">{passed} of {len(rows)} checks passed. NOT MATCHING: {names}</div>'
    if final is not None:
        same = final.content_hash == h
        strip += (f'<div class="strip">Finalised {final.finalised_at:%d-%m-%Y %H:%M} (code {final.content_hash})'
                  + ("" if same else ' <span class="bad">&mdash; figures have changed since</span>') + "</div>")

    # bank status beside each payment mode
    status_by_mode = {c.mode: c.status for c in services.bank.build_days(day, day)}
    reverse = {v: k for k, v in REPORT_LABELS.items()}
    bank_status = {}
    for s in report.shifts:
        for label, _ in s.lines:
            mode = reverse.get(label)
            if mode in status_by_mode:
                bank_status[(s.number, label)] = "bank: matched" if status_by_mode[mode] == "matched" else "bank: pending"

    # dip difference per tank, as a percentage, against the tolerance (T-02)
    tol = services.pump_settings.get_decimal("dip_tolerance_percent")
    cells = []
    for c in report.tanks:
        diff, stock = report.plus_minus.get(c.tank_id), report.total_stock.get(c.tank_id)
        if diff is None or not stock:
            cells.append(f"<td>{_e(c.code)}</td><td>no dip taken</td><td></td><td></td>")
            continue
        pct = diff / stock * Decimal("100")
        flag = "OUTSIDE" if abs(pct) > tol else "ok"
        cells.append(f'<td>{_e(c.code)}</td><td class="n">{litres(diff)}</td><td class="n">{pct:.2f}%</td>'
                     f'<td class="{"bad" if flag == "OUTSIDE" else ""}">{flag} (tolerance {tol}%)</td>')
    dip = ("<h2>Dip difference</h2><table><tr><th>Tank</th><th class='n'>Litres</th><th class='n'>% of stock</th><th>Against tolerance</th></tr>"
           + "".join(f"<tr>{c}</tr>" for c in cells) + "</table>")

    b = report.bowser
    bowser = ""
    if b is not None and (b.bills or b.meter is not None):
        if b.meter_net is None:
            bowser = '<div class="strip bad">Bowser: no meter reading recorded for this day</div>'
        elif b.meter_net == b.bills_qty:
            bowser = f'<div class="strip">Bowser: meter Net Sale {litres(b.meter_net)} L equals the litres on the bills &mdash; PASS</div>'
        else:
            bowser = (f'<div class="strip bad">Bowser: meter Net Sale {litres(b.meter_net)} L but bills add up to '
                      f'{litres(b.bills_qty)} L &mdash; FAIL</div>')

    new_credit = sum((s.credit_total for s in report.shifts), _Z)
    outstanding, over, overdue = _Z, [], []
    for acct in services.credit_ledger.chase_accounts():
        v = services.credit_ledger.view(acct.customer_id, day)
        outstanding += max(_Z, v.summary.balance)
        if v.credit_limit is not None and v.summary.balance > v.credit_limit:
            over.append(v.name)
        if v.overdue and v.summary.balance > 0:
            overdue.append(v.name)
    credit = (f"<h2>Credit</h2><table><tr><td>New credit given today</td><td class='n'>{inr(new_credit)}</td></tr>"
              f"<tr><td>Total outstanding from customers</td><td class='n'>{inr(outstanding)}</td></tr>"
              f"<tr><td>Customers over their limit</td><td>{_e(', '.join(over)) or 'none'}</td></tr>"
              f"<tr><td>Customers overdue</td><td>{_e(', '.join(overdue)) or 'none'}</td></tr></table>")

    signatures = (f'<div class="sign"><span>Prepared by: {_e(who)}</span><span>Checked by:</span></div>')
    now = datetime.now().strftime("%d-%m-%Y %H:%M")
    footer = f'<div class="foot">Generated {now} &middot; page {{page}} of 2 &middot; report code {h}</div>'
    return {
        "style": "plus", "title": "DAILY REPORT (Plus)", "strip_html": strip, "bank_status": bank_status, "grid_extra_html": dip,
        "bowser_extra_html": bowser, "front_extra_html": credit, "back_extra_html": signatures, "footer_html": footer,
    }
