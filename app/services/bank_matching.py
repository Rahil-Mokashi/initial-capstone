"""Deterministic matching of what the books say should reach the bank against what the bank statement shows.

No AI, no scoring: the same inputs always give the same answer, and every proposal says which rule made it.
Defaults are conservative. Only two cases are matched without a person: the bank line carries the expected
payment's reference, or exactly one expected amount and exactly one bank line fit each other (same amount,
inside the date window). Everything else (a fee was deducted, several payments arrived as one credit, one
payment arrived in pieces, or more than one pairing could fit) is a SUGGESTION a person confirms.

Pure functions over small dataclasses; the service stores the result.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

_Z = Decimal("0")
MAX_SUBSET = 6
MAX_CANDIDATES = 18
REVERSAL_WORDS = ("reversal", " rev ", "rev-", "/rev", "refund", "return", "chargeback", "chargeback", "failed")


@dataclass
class Expected:
    id: str
    amount: Decimal
    win_from: date
    win_to: date
    reference: Optional[str] = None
    direction: str = "credit"  # money coming in ("credit" on the statement) or going out ("debit")
    accounts: Set[str] = field(default_factory=set)  # bank accounts this payment may land in; empty = any


@dataclass
class Line:
    id: str
    txn_date: date
    credit: Decimal
    debit: Decimal
    description: str = ""
    reference: Optional[str] = None
    account_id: str = ""

    def amount_for(self, direction: str) -> Decimal:
        return self.credit if direction == "credit" else self.debit


@dataclass
class Proposal:
    kind: str  # reference | amount_date | many_to_one | one_to_many
    expected_ids: List[str]
    line_ids: List[str]
    auto: bool
    charges: Decimal  # expected total - received total: what was deducted on the way (never negative)
    note: str = ""


def _fits_fee(expected_total: Decimal, received: Decimal, fee_pct: Decimal) -> bool:
    """Received is the expected amount, or a little less (charges deducted before settlement), never more."""
    if received > expected_total or received <= 0:
        return False
    return received >= expected_total * (Decimal("1") - fee_pct / Decimal("100"))


def _ok_account(e: Expected, ln: Line) -> bool:
    return not e.accounts or ln.account_id in e.accounts


def _in_window(e: Expected, ln: Line) -> bool:
    return e.win_from <= ln.txn_date <= e.win_to


def _mentions(ln: Line, reference: str) -> bool:
    ref = reference.strip().lower()
    return bool(ref) and (ref == (ln.reference or "").strip().lower() or ref in (ln.description or "").lower())


def propose(expected: List[Expected], lines: List[Line], fee_pct: Decimal = Decimal("2")) -> List[Proposal]:
    exps = sorted(expected, key=lambda e: (e.win_from, e.id))
    rows = sorted(lines, key=lambda r: (r.txn_date, r.id))
    used_e: Set[str] = set()
    used_r: Set[str] = set()
    out: List[Proposal] = []

    def take(p: Proposal):
        used_e.update(p.expected_ids)
        used_r.update(p.line_ids)
        out.append(p)

    # 1. the bank line carries the payment's own reference (UTR / RRN / batch number)
    for e in exps:
        if not e.reference:
            continue
        for ln in rows:
            if ln.id in used_r or not _ok_account(e, ln) or not _mentions(ln, e.reference):
                continue
            got = ln.amount_for(e.direction)
            if got <= 0:
                continue
            exact = got == e.amount
            if exact or _fits_fee(e.amount, got, fee_pct):
                take(Proposal("reference", [e.id], [ln.id], auto=True, charges=e.amount - got,
                              note="same reference" + ("" if exact else "; the bank deducted a charge")))
            else:
                take(Proposal("reference", [e.id], [ln.id], auto=False, charges=max(_Z, e.amount - got),
                              note=f"same reference, but the amount differs ({got} against {e.amount})"))
            break

    # 2. one expected payment and one bank line with the same amount inside the date window
    def candidates_for(e: Expected, exact_only: bool):
        res = []
        for ln in rows:
            if ln.id in used_r or not _ok_account(e, ln) or not _in_window(e, ln):
                continue
            got = ln.amount_for(e.direction)
            if (got == e.amount) if exact_only else _fits_fee(e.amount, got, fee_pct):
                res.append(ln)
        return res

    for e in [x for x in exps if x.id not in used_e]:
        cands = candidates_for(e, exact_only=True)
        if len(cands) == 1:
            ln = cands[0]
            rivals = [x for x in exps if x.id not in used_e and x.id != e.id and _ok_account(x, ln) and _in_window(x, ln)
                      and x.direction == e.direction and ln.amount_for(x.direction) == x.amount]
            if not rivals:
                take(Proposal("amount_date", [e.id], [ln.id], auto=True, charges=_Z, note="same amount, inside the date window"))
                continue
        if cands:
            ln = min(cands, key=lambda c: (abs((c.txn_date - e.win_from).days), c.id))
            take(Proposal("amount_date", [e.id], [ln.id], auto=False, charges=_Z,
                          note="same amount, but more than one payment or bank line could fit: please check"))
            continue
        near = candidates_for(e, exact_only=False)
        if near:
            ln = min(near, key=lambda c: (abs((c.txn_date - e.win_from).days), c.id))
            got = ln.amount_for(e.direction)
            take(Proposal("amount_date", [e.id], [ln.id], auto=False, charges=e.amount - got,
                          note="a little less than expected: a bank charge may have been deducted"))

    # 3. several expected payments settled as ONE bank credit
    for ln in [r for r in rows if r.id not in used_r]:
        direction = "credit" if ln.credit > 0 else "debit"
        got = ln.amount_for(direction)
        pool = [e for e in exps if e.id not in used_e and e.direction == direction and _ok_account(e, ln) and _in_window(e, ln)
                and e.amount <= got * Decimal("100") / (Decimal("100") - fee_pct)]
        pool = pool[:MAX_CANDIDATES]
        found = _subsets(pool, lambda sub: _fits_fee(sum((x.amount for x in sub), _Z), got, fee_pct), lambda x: x.amount)
        if found:
            exact = [s for s in found if sum((x.amount for x in s), _Z) == got]
            pick = exact[0] if len(exact) == 1 else (found[0] if len(found) == 1 else None)
            if pick:
                total = sum((x.amount for x in pick), _Z)
                take(Proposal("many_to_one", [x.id for x in pick], [ln.id], auto=False, charges=total - got,
                              note=f"{len(pick)} payments added up to this one bank credit"))

    # 4. ONE expected payment that arrived in several bank lines
    for e in [x for x in exps if x.id not in used_e]:
        pool = [r for r in rows if r.id not in used_r and _ok_account(e, r) and _in_window(e, r) and 0 < r.amount_for(e.direction) < e.amount]
        pool = pool[:MAX_CANDIDATES]
        found = _subsets(pool, lambda sub: _fits_fee(e.amount, sum((x.amount_for(e.direction) for x in sub), _Z), fee_pct),
                         lambda x: x.amount_for(e.direction))
        if len(found) == 1:
            sub = found[0]
            got = sum((x.amount_for(e.direction) for x in sub), _Z)
            take(Proposal("one_to_many", [e.id], [x.id for x in sub], auto=False, charges=e.amount - got,
                          note=f"arrived in {len(sub)} pieces"))
    return out


def _subsets(pool, accept, value) -> List[tuple]:
    """Every subset of 2..MAX_SUBSET items that `accept`s, smallest first, found in a fixed order."""
    found = []
    for size in range(2, min(MAX_SUBSET, len(pool)) + 1):
        for combo in combinations(pool, size):
            if accept(combo):
                found.append(combo)
                if len(found) > 3:
                    return found
    return found


def find_reversals(lines: List[Line], max_days: int = 10) -> List[Tuple[str, str]]:
    """(credit line id, reversing debit line id): a bank debit that undoes an earlier credit of the same amount."""
    credits = sorted([r for r in lines if r.credit > 0], key=lambda r: (r.txn_date, r.id))
    taken: Set[str] = set()
    pairs: List[Tuple[str, str]] = []
    for d in sorted([r for r in lines if r.debit > 0], key=lambda r: (r.txn_date, r.id)):
        text = f" {(d.description or '').lower()} "
        keyword = any(w in text for w in REVERSAL_WORDS)
        for c in credits:
            if c.id in taken or c.credit != d.debit or not (0 <= (d.txn_date - c.txn_date).days <= max_days):
                continue
            same_ref = bool(d.reference) and d.reference == c.reference
            if keyword or same_ref:
                pairs.append((c.id, d.id))
                taken.add(c.id)
                break
    return pairs


def window_for(business_date: date, window_days: int) -> Tuple[date, date]:
    """Today's takings can reach the bank the same day up to `window_days` later (covers T+1 and a weekend)."""
    return business_date, business_date + timedelta(days=window_days)
