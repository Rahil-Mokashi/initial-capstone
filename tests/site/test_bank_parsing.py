"""Reading statements: CSV and XLSX, saved column mappings, duplicate detection, running-balance continuity."""

import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.services.bank_parsing import (
    Mapping,
    check_continuity,
    extract_reference,
    parse_amount,
    parse_rows,
    read_table,
    row_hash,
)

D = Decimal

CSV = """Statement of account
Account 0000
Txn Date,Narration,Withdrawal,Deposit,Balance
09/10/2026,UPI/412345678901/PAYTM,,"4,147.60","1,04,147.60"
10/10/2026,CASH DEPOSIT SELF,,"20,000.00","1,24,147.60"
10/10/2026,CHARGES,15.00,,"1,24,132.60"
"""
MAP = Mapping(date_col="Txn Date", description_col="Narration", debit_col="Withdrawal", credit_col="Deposit", balance_col="Balance",
              date_format="%d/%m/%Y", header_row=2)


def parsed():
    headers, rows = read_table("stmt.csv", CSV.encode(), MAP)
    return parse_rows(headers, rows, MAP)


def test_csv_with_lines_before_the_header_and_indian_number_grouping():
    rows, problems = parsed()
    assert problems == [] and len(rows) == 3
    assert (rows[0].txn_date, rows[0].credit, rows[0].debit, rows[0].balance) == (date(2026, 10, 9), D("4147.60"), D("0"), D("104147.60"))
    assert rows[2].debit == D("15.00") and rows[2].credit == 0
    assert rows[0].reference == "412345678901"  # the UPI reference is read out of the narration


def test_xlsx_with_real_dates_and_numbers():
    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Debit", "Credit", "Balance"])
    ws.append([date(2026, 10, 9), "NEFT HDFCR52026100912345678", None, 5000.5, 15000.5])
    ws.append([date(2026, 10, 10), "CASH WDL", 100, None, 14900.5])
    buf = io.BytesIO()
    wb.save(buf)
    m = Mapping(date_col="Date", description_col="Description", debit_col="Debit", credit_col="Credit", balance_col="Balance")
    headers, rows = read_table("s.xlsx", buf.getvalue(), m)
    got, problems = parse_rows(headers, rows, m)
    assert problems == [] and [(r.credit, r.debit) for r in got] == [(D("5000.5"), D("0")), (D("0"), D("100"))]
    assert got[0].reference == "HDFCR52026100912345678"


def test_single_signed_amount_column_and_a_dr_cr_column():
    csv_text = "Date,Details,Amount,DrCr\n01-10-2026,A,100.00,CR\n02-10-2026,B,40.00,DR\n"
    m = Mapping(date_col="Date", description_col="Details", amount_col="Amount", type_col="DrCr")
    headers, rows = read_table("x.csv", csv_text.encode(), m)
    got, _ = parse_rows(headers, rows, m)
    assert [(r.credit, r.debit) for r in got] == [(D("100.00"), D("0")), (D("0"), D("40.00"))]
    signed = Mapping(date_col="Date", description_col="Details", amount_col="Amount")
    h2, r2 = read_table("x.csv", "Date,Details,Amount\n01-10-2026,A,-250.00\n02-10-2026,B,(75.00)\n03-10-2026,C,10\n".encode(), signed)
    got2, _ = parse_rows(h2, r2, signed)
    assert [(r.credit, r.debit) for r in got2] == [(D("0"), D("250.00")), (D("0"), D("75.00")), (D("10"), D("0"))]


def test_amounts_and_dates_that_cannot_be_read_are_reported_with_their_line_not_skipped_silently():
    text = "Date,Narr,Debit,Credit\n01/10/2026,ok,,100\nnot-a-date,bad date,,50\n03/10/2026,bad amt,abc,\n04/10/2026,both,5,5\n05/10/2026,none,,\n"
    m = Mapping(date_col="Date", description_col="Narr", debit_col="Debit", credit_col="Credit", date_format="%d/%m/%Y")
    headers, rows = read_table("x.csv", text.encode(), m)
    got, problems = parse_rows(headers, rows, m)
    assert len(got) == 1
    assert [p.line_no for p in problems] == [3, 4, 5, 6]
    assert "date" in problems[0].message and "amount" in problems[1].message and "both" in problems[2].message and "no amount" in problems[3].message


def test_a_missing_column_or_a_pdf_is_refused_with_a_plain_message():
    m = Mapping(date_col="Nope", description_col="Narration", debit_col="Withdrawal")
    headers, rows = read_table("s.csv", CSV.encode(), Mapping(date_col="x", description_col="y", header_row=2))
    with pytest.raises(ValueError, match="no column called 'Nope'"):
        parse_rows(headers, rows, m)
    with pytest.raises(ValueError, match="PDF"):
        read_table("statement.pdf", b"%PDF-1.4", None)


def test_reference_extraction():
    assert extract_reference("UPI/412345678901/PAYTM") == "412345678901"
    assert extract_reference("NEFT-HDFCR52026100912345678-ACME") == "HDFCR52026100912345678"
    assert extract_reference("CASH DEPOSIT SELF") is None
    assert parse_amount("1,23,456.78") == D("123456.78") and parse_amount("") == 0 and parse_amount("500 Dr") == D("-500")


def test_the_same_line_always_hashes_the_same_and_a_different_one_differently():
    a, _ = parsed()
    b, _ = parsed()
    assert [row_hash("acc", r) for r in a] == [row_hash("acc", r) for r in b]
    assert len({row_hash("acc", r) for r in a}) == 3
    assert row_hash("acc", a[0]) != row_hash("other-account", a[0])


def test_balances_that_add_up_give_the_opening_and_closing_and_no_breaks():
    rows, _ = parsed()
    opening, closing, breaks = check_continuity(rows)
    assert (opening, closing, breaks) == (D("100000.00"), D("124132.60"), [])


def test_a_missing_row_shows_up_as_a_break_with_the_size_of_the_gap():
    rows, _ = parsed()
    del rows[1]  # the 20,000 cash deposit line never made it into the file
    _, _, breaks = check_continuity(rows)
    # the balance is 20,000 higher than the rows add up to: a credit of 20,000 is missing from the file
    assert len(breaks) == 1 and breaks[0].gap == D("20000.00")
    assert breaks[0].line_no == rows[1].line_no


def test_a_newest_first_file_is_understood():
    rows, _ = parsed()
    opening, closing, breaks = check_continuity(list(reversed(rows)))
    assert (opening, closing, breaks) == (D("100000.00"), D("124132.60"), [])


def test_rows_without_balances_cannot_be_checked_and_say_so():
    m = Mapping(date_col="Date", description_col="Narr", debit_col="Debit", credit_col="Credit")
    headers, rows = read_table("x.csv", "Date,Narr,Debit,Credit\n01/10/2026,a,,5\n".encode(), m)
    got, _ = parse_rows(headers, rows, m)
    assert check_continuity(got) == (None, None, [])
