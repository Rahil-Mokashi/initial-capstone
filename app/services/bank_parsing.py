"""Reading a bank statement file (CSV or XLSX) into plain rows, with a saved column mapping per bank.

Pure functions: no database, no permissions. PDF statements are out of scope (questionnaire H-07): a bank
that only gives PDFs must export CSV/XLSX first. Nothing is guessed silently: a row that cannot be read is
reported with its line number and the reason, and the import preview shows it before anything is stored.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

_Z = Decimal("0")
DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%m/%d/%Y")


@dataclass
class Mapping:
    """Which column holds what (column NAMES from the header row, as the bank prints them)."""

    date_col: str
    description_col: str
    debit_col: Optional[str] = None  # separate debit / credit columns...
    credit_col: Optional[str] = None
    amount_col: Optional[str] = None  # ...or one signed amount (negative = money out)...
    type_col: Optional[str] = None  # ...or one amount plus a Dr/Cr (or DR/CR) column
    balance_col: Optional[str] = None
    reference_col: Optional[str] = None
    date_format: Optional[str] = None  # None = try the common ones
    header_row: int = 0  # 0-based index of the header line (banks often print a few lines first)
    delimiter: Optional[str] = None  # CSV only; None = sniff
    sheet: Optional[str] = None  # XLSX only; None = first sheet

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @staticmethod
    def from_json(d: dict) -> "Mapping":
        return Mapping(**{k: d.get(k) for k in Mapping.__dataclass_fields__ if k in d})


@dataclass
class ParsedRow:
    line_no: int
    txn_date: date
    description: str
    debit: Decimal
    credit: Decimal
    balance: Optional[Decimal]
    reference: Optional[str]
    raw: Dict[str, str] = field(default_factory=dict)


@dataclass
class Problem:
    line_no: int
    message: str


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def read_table(filename: str, content: bytes, mapping: Optional[Mapping] = None) -> Tuple[List[str], List[List[str]]]:
    """(headers, rows) from a CSV or XLSX file. The header row is where the mapping says (default: the first line)."""
    name = filename.lower()
    header_row = mapping.header_row if mapping else 0
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb[mapping.sheet] if mapping and mapping.sheet else wb[wb.sheetnames[0]]
        lines = [[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
    elif name.endswith(".csv") or name.endswith(".txt"):
        text = content.decode("utf-8-sig", errors="replace")
        delimiter = mapping.delimiter if mapping and mapping.delimiter else _sniff(text)
        lines = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    else:
        raise ValueError("Only CSV and Excel (.xlsx) statements can be imported. PDF statements are not supported yet.")
    lines = [r for r in lines if any(c for c in r)]
    if len(lines) <= header_row:
        raise ValueError("The file has no rows under its header")
    headers = lines[header_row]
    return headers, lines[header_row + 1:]


def _sniff(text: str) -> str:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def parse_amount(text: str) -> Decimal:
    t = (text or "").strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    if t in ("", "-"):
        return _Z
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    suffix = ""
    if t[-2:].upper() in ("DR", "CR"):
        suffix, t = t[-2:].upper(), t[:-2].strip()
    try:
        value = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"'{text}' is not an amount") from None
    if neg:
        value = -value
    if suffix == "DR":
        value = -abs(value)
    elif suffix == "CR":
        value = abs(value)
    return value


def parse_date(text: str, fmt: Optional[str]) -> date:
    t = (text or "").strip()
    if not t:
        raise ValueError("no date")
    for f in ([fmt] if fmt else []) + list(DATE_FORMATS):
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    if re.match(r"^\d{4}-\d{2}-\d{2}", t):
        return date.fromisoformat(t[:10])
    raise ValueError(f"'{text}' is not a date" + (f" in the format {fmt}" if fmt else ""))


_REF_PATTERNS = (
    re.compile(r"(?<!\d)\d{12}(?!\d)"),  # UPI RRN / IMPS reference: 12 digits
    re.compile(r"\b[A-Z]{4}[A-Z0-9]\d{10,17}\b"),  # NEFT/RTGS UTR such as HDFCR52024...
    re.compile(r"\b[A-Z]{4}\d{14,18}\b"),
)


def extract_reference(description: str) -> Optional[str]:
    for pat in _REF_PATTERNS:
        m = pat.search(description or "")
        if m:
            return m.group(0)
    return None


def parse_rows(headers: List[str], rows: List[List[str]], mapping: Mapping) -> Tuple[List[ParsedRow], List[Problem]]:
    index = {h.strip().lower(): i for i, h in enumerate(headers)}

    def col(name: Optional[str]) -> Optional[int]:
        if not name:
            return None
        key = name.strip().lower()
        if key not in index:
            raise ValueError(f"The file has no column called '{name}'. Columns found: {', '.join(headers)}")
        return index[key]

    di, si, dbi, cri = col(mapping.date_col), col(mapping.description_col), col(mapping.debit_col), col(mapping.credit_col)
    ai, ti, bi, ri = col(mapping.amount_col), col(mapping.type_col), col(mapping.balance_col), col(mapping.reference_col)
    if dbi is None and cri is None and ai is None:
        raise ValueError("Say which column holds the money: debit and credit columns, or one amount column")

    out: List[ParsedRow] = []
    problems: List[Problem] = []
    for n, r in enumerate(rows, start=mapping.header_row + 2):
        def get(i):
            return r[i] if i is not None and i < len(r) else ""

        try:
            when = parse_date(get(di), mapping.date_format)
            debit, credit = _Z, _Z
            if ai is not None:
                amount = parse_amount(get(ai))
                kind = get(ti).strip().upper() if ti is not None else ""
                if kind.startswith("D"):
                    debit = abs(amount)
                elif kind.startswith("C"):
                    credit = abs(amount)
                elif amount < 0:
                    debit = -amount
                else:
                    credit = amount
            else:
                debit = abs(parse_amount(get(dbi))) if dbi is not None else _Z
                credit = abs(parse_amount(get(cri))) if cri is not None else _Z
            if debit and credit:
                raise ValueError("a row cannot be both a debit and a credit")
            if not debit and not credit:
                raise ValueError("no amount")
            bal_text = get(bi)
            balance = parse_amount(bal_text) if bi is not None and bal_text.strip() else None
            desc = get(si)
            ref = get(ri).strip() if ri is not None and get(ri).strip() else extract_reference(desc)
            out.append(ParsedRow(n, when, desc, debit, credit, balance, ref, {h: get(i) for i, h in enumerate(headers)}))
        except ValueError as exc:
            problems.append(Problem(n, str(exc)))
    return out, problems


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def row_hash(account_id: str, row: ParsedRow) -> str:
    """Same line of the same statement => same hash, so importing a file twice (or two overlapping files) adds nothing."""
    parts = [account_id, row.txn_date.isoformat(), str(row.credit - row.debit), normalise(row.description), (row.reference or "").lower(),
             "" if row.balance is None else str(row.balance)]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


@dataclass
class ContinuityProblem:
    line_no: int
    expected_balance: Decimal
    found_balance: Decimal

    @property
    def gap(self) -> Decimal:
        return self.found_balance - self.expected_balance


def check_continuity(rows: List[ParsedRow]) -> Tuple[Optional[Decimal], Optional[Decimal], List[ContinuityProblem]]:
    """(opening balance, closing balance, breaks). Row balance = previous balance + credit - debit, or a row is missing.

    The opening balance is worked back from the first row; every later row is checked against the one before it.
    Rows are taken in file order; banks print oldest-first or newest-first, so a newest-first file is reversed
    when its balances only add up that way.
    """
    with_bal = [r for r in rows if r.balance is not None]
    if not with_bal:
        return None, None, []

    def breaks_in(seq: List[ParsedRow]) -> List[ContinuityProblem]:
        found = []
        for prev, cur in zip(seq, seq[1:]):
            expected = prev.balance + cur.credit - cur.debit
            if expected != cur.balance:
                found.append(ContinuityProblem(cur.line_no, expected, cur.balance))
        return found

    forward = breaks_in(with_bal)
    backward_seq = list(reversed(with_bal))
    backward = breaks_in(backward_seq)
    seq, breaks = (backward_seq, backward) if len(backward) < len(forward) else (with_bal, forward)
    opening = seq[0].balance - seq[0].credit + seq[0].debit
    return opening, seq[-1].balance, breaks
