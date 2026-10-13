"""Bank reconciliation end to end on the synthetic pump day: import (preview, duplicates, missing rows), expected
receipts from the books, matching (reference, amount + date, batch settlement, charges, T+1, reversal), manual
match and unmatch with a reason, the owner's lock, 'not ours', the checks, and permissions."""

import base64
from datetime import date, timedelta
from decimal import Decimal

import pytest

from api_helpers import audit_chain_ok, audit_events
from pump_day import TODAY, build_day
from test_api_daily_report import day  # noqa: F401  (fixture)

D = Decimal
T = date.today()
MAP = {"date_col": "Date", "description_col": "Narration", "debit_col": "Withdrawal", "credit_col": "Deposit",
       "balance_col": "Balance", "date_format": "%d/%m/%Y"}


def stmt(rows, opening="100000.00"):
    """rows: (date, narration, credit, debit). Builds a CSV whose running balance adds up."""
    bal = D(opening)
    lines = ["Date,Narration,Withdrawal,Deposit,Balance"]
    for when, text, credit, debit in rows:
        bal += D(credit) - D(debit)
        lines.append(f'{when:%d/%m/%Y},{text},{debit if D(debit) else ""},{credit if D(credit) else ""},{bal}')
    return "\n".join(lines) + "\n"


def b64(text):
    return base64.b64encode(text.encode()).decode()


def body(text, name="s.csv", **extra):
    return {"filename": name, "content_base64": b64(text), "mapping": MAP, **extra}


@pytest.fixture()
def banks(client, day, accountant):
    # Which mode lands where is open (H-02), so it is a setting per account: here the payment apps settle into one account
    # and cash is deposited into two others, named exactly as the cash book names them.
    wallet = client.post("/api/bank/accounts", headers=accountant, json={"name": "Wallet Bank", "account_mask": "XXXX1111", "modes": ["Paytm", "PhonePe", "DTP Card", "Card"]}).json()
    boi = client.post("/api/bank/accounts", headers=accountant, json={"name": "Bank of India", "account_mask": "XXXX1234", "modes": ["cash_deposit"]}).json()
    second = client.post("/api/bank/accounts", headers=accountant, json={"name": "Second Bank", "account_mask": "XXXX9876", "modes": ["cash_deposit"]}).json()
    return {"wallet": wallet, "boi": boi, "second": second}


def _import(client, h, acct, text, **extra):
    r = client.post(f"/api/bank/accounts/{acct['id']}/import", headers=h, json=body(text, **extra))
    assert r.status_code == 201, r.text
    return r.json()


def _run(client, h, d_from=T, d_to=T):
    r = client.post("/api/bank/match/run", headers=h, json={"date_from": d_from.isoformat(), "date_to": d_to.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def _days(client, h, d_from=T, d_to=T):
    rows = client.get(f"/api/bank/days?date_from={d_from}&date_to={d_to}", headers=h).json()
    return {r["mode"]: r for r in rows}


MAIN = [  # the payment-app account on the synthetic day: the books expect Paytm 50,000 (two shifts), PhonePe 6,000 (two), DTP 10,000
    (T, "UPI PAYTM SETTLEMENT BATCH", "50000.00", "0"),
    (T, "PHONEPE SETTLEMENT", "5950.00", "0"),
    (T, "DTP FLEET CARD SETTLEMENT", "10000.00", "0"),
    (T, "TRUST DONATION RECEIVED", "777.00", "0"),
]


# ------------------------------------------------------------------------------------------ accounts and permissions
def test_accounts_modes_and_who_may_do_what(client, day, manager, accountant, owner, attendant, data_entry, session_factory):
    a = client.post("/api/bank/accounts", headers=accountant, json={"name": "Bank of India", "modes": ["Paytm"]})
    assert a.status_code == 201 and a.json()["modes"] == ["Paytm"]
    assert client.post("/api/bank/accounts", headers=accountant, json={"name": "Bank of India"}).status_code == 409
    assert client.post("/api/bank/accounts", headers=accountant, json={"name": "X", "modes": ["Bitcoin"]}).status_code == 422
    changed = client.put(f"/api/bank/accounts/{a.json()['id']}/modes", headers=owner, json={"modes": ["Paytm", "PhonePe"]}).json()
    assert changed["modes"] == ["Paytm", "PhonePe"]
    assert [m["mode"] for m in client.get("/api/bank/modes", headers=owner).json()][:5] == ["Paytm", "PhonePe", "DTP Card", "Card", "Other"]
    for h in (manager, attendant, data_entry):  # H-24: only the accountant and the owners, by default
        assert client.get("/api/bank/accounts", headers=h).status_code == 403
        assert client.post("/api/bank/accounts", headers=h, json={"name": "Y"}).status_code == 403
    assert client.get("/api/bank/accounts", headers={"X-Launch-Secret": client.headers["X-Launch-Secret"]}).status_code == 401
    assert audit_events(session_factory, "bank_account_created") and audit_events(session_factory, "bank_account_modes_changed")


# ------------------------------------------------------------------------------------------ importing statements
def test_preview_shows_what_would_happen_and_stores_nothing(client, banks, accountant):
    text = stmt(MAIN)
    p = client.post(f"/api/bank/accounts/{banks['wallet']['id']}/preview", headers=accountant, json=body(text)).json()
    assert (p["row_count"], p["new_rows"], p["duplicate_rows"], p["problems"], p["breaks"]) == (4, 4, 0, [], [])
    assert p["opening_balance"] == "100000.00" and p["closing_balance"] == "166727.00" and p["same_file_before"] is False
    assert p["sample"][0]["credit"] == "50000.00"
    assert client.get(f"/api/bank/rows?date_from={T}&date_to={T}", headers=accountant).json() == []


def test_importing_twice_adds_nothing_the_second_time(client, banks, accountant, session_factory):
    text = stmt(MAIN)
    first = _import(client, accountant, banks["wallet"], text)
    assert (first["row_count"], first["new_rows"], first["duplicate_rows"], first["continuity_ok"]) == (4, 4, 0, True)
    second = _import(client, accountant, banks["wallet"], text)
    assert (second["new_rows"], second["duplicate_rows"]) == (0, 4)
    assert len(client.get(f"/api/bank/rows?date_from={T}&date_to={T}", headers=accountant).json()) == 4
    again = client.post(f"/api/bank/accounts/{banks['wallet']['id']}/preview", headers=accountant, json=body(text)).json()
    assert again["same_file_before"] is True and again["new_rows"] == 0
    assert audit_events(session_factory, "bank_statement_imported") and audit_chain_ok(session_factory)


def test_a_file_that_overlaps_an_earlier_one_only_adds_the_new_lines(client, banks, accountant):
    first = stmt(MAIN[:3])
    _import(client, accountant, banks["wallet"], first)
    overlapping = stmt(MAIN)  # the same three lines (same running balances), plus one more
    r = _import(client, accountant, banks["wallet"], overlapping, name="later.csv")
    assert (r["new_rows"], r["duplicate_rows"]) == (1, 3)


def test_missing_rows_are_flagged_with_the_size_of_the_gap_and_the_import_says_so(client, banks, accountant, owner):
    text = stmt(MAIN)
    lines = text.splitlines()
    del lines[3]  # the DTP line never made it into the file
    rec = _import(client, accountant, banks["wallet"], "\n".join(lines) + "\n")
    assert rec["continuity_ok"] is False and rec["break_count"] == 1 and "missing" in rec["continuity_notes"]
    client.post("/api/checks/run", headers=owner, json={"day": TODAY})
    checks = [c for c in client.get(f"/api/checks?day={TODAY}", headers=owner).json()["results"] if c["key"] == "bank.statement_has_no_missing_rows"]
    assert checks and checks[0]["status"] == "fail" and checks[0]["actual"] == "1"


def test_unreadable_lines_stop_the_import_unless_skipped_on_purpose(client, banks, accountant):
    text = stmt(MAIN[:2]) + "not-a-date,BROKEN,,100,5\n"
    refused = client.post(f"/api/bank/accounts/{banks['wallet']['id']}/import", headers=accountant, json=body(text))
    assert refused.status_code == 422 and "cannot be read" in refused.json()["error"]["message"]
    ok = client.post(f"/api/bank/accounts/{banks['wallet']['id']}/import", headers=accountant, json=body(text, skip_unreadable=True))
    assert ok.status_code == 201 and ok.json()["new_rows"] == 2 and "skipped on purpose" in ok.json()["continuity_notes"]


def test_pdf_and_wrong_columns_are_refused_in_plain_words(client, banks, accountant):
    r = client.post(f"/api/bank/accounts/{banks['wallet']['id']}/preview", headers=accountant, json=body("%PDF-1.4", name="statement.pdf"))
    assert r.status_code == 422 and "PDF" in r.json()["error"]["message"]
    bad = {**body(stmt(MAIN)), "mapping": {**MAP, "date_col": "When"}}
    r2 = client.post(f"/api/bank/accounts/{banks['wallet']['id']}/preview", headers=accountant, json=bad)
    assert r2.status_code == 422 and "no column called 'When'" in r2.json()["error"]["message"]


def test_a_column_layout_is_saved_per_bank(client, banks, accountant):
    saved = client.put(f"/api/bank/accounts/{banks['wallet']['id']}/profiles/Net banking CSV", headers=accountant, json=MAP)
    assert saved.status_code == 200
    listed = client.get(f"/api/bank/accounts/{banks['wallet']['id']}/profiles", headers=accountant).json()
    assert listed == [{"name": "Net banking CSV", "mapping": {**{k: None for k in ("amount_col", "type_col", "reference_col", "delimiter", "sheet")}, **MAP, "header_row": 0}}]
    assert client.get(f"/api/bank/accounts/{banks['second']['id']}/profiles", headers=accountant).json() == []


# ------------------------------------------------------------------------------------------ matching the day
def test_the_synthetic_day_matches_the_way_the_rules_say(client, banks, accountant, session_factory):
    _import(client, accountant, banks["wallet"], stmt(MAIN))
    _import(client, accountant, banks["boi"], stmt([(T, "CASH DEPOSIT SELF", "50000.00", "0")], opening="8000.00"))
    _import(client, accountant, banks["second"], stmt([(T, "CASH DEPOSIT SELF", "20000.00", "0")], opening="5000.00"))
    made = _run(client, accountant)
    # auto: DTP 10,000 (one amount, one line), cash 50,000 to Bank of India, cash 20,000 to Second Bank; suggested: the two batches
    assert made == {"auto": 3, "suggested": 2, "reversals": 0}
    sugg = client.get("/api/bank/suggestions", headers=accountant).json()
    kinds = {s["rule"] for s in sugg}
    assert kinds == {"many_to_one"} and len(sugg) == 2
    by_charges = {s["charges"]: s for s in sugg}
    assert set(by_charges) == {"0.00", "50.00"}  # Paytm 50,000 exactly; PhonePe 5,950 against 6,000: 50 deducted by the bank
    assert sum(D(e["amount"]) for e in by_charges["50.00"]["expected"]) == D("6000.00")
    for s in sugg:
        assert client.post(f"/api/bank/matches/{s['match_id']}/confirm", headers=accountant).status_code == 200
    days = _days(client, accountant)
    assert (days["Paytm"]["expected"], days["Paytm"]["received"], days["Paytm"]["status"]) == ("50000.00", "50000.00", "matched")
    assert (days["PhonePe"]["expected"], days["PhonePe"]["received"], days["PhonePe"]["charges"], days["PhonePe"]["status"]) == ("6000.00", "5950.00", "50.00", "matched")
    assert (days["DTP Card"]["received"], days["DTP Card"]["status"]) == ("10000.00", "matched")
    # cash deposits: 130,000 expected; 70,000 reached the bank; the 60,000 deposit is not on the statement yet
    assert (days["cash_deposit"]["expected"], days["cash_deposit"]["received"], days["cash_deposit"]["unmatched"], days["cash_deposit"]["status"]) == (
        "130000.00", "70000.00", "60000.00", "awaiting")
    ex = client.get(f"/api/bank/exceptions?date_from={T}&date_to={T}", headers=accountant).json()
    assert [r["description"] for r in ex["unmatched_credits"]] == ["TRUST DONATION RECEIVED"]
    assert [a["expected"]["amount"] for a in ex["aged_expected"]] == ["60000.00"] and ex["total_charges"] == "50.00"
    assert audit_events(session_factory, "bank_match_auto") and audit_events(session_factory, "bank_match_confirmed")
    assert audit_chain_ok(session_factory)


def test_a_credit_that_is_not_the_pumps_is_marked_not_ours_with_a_reason(client, banks, accountant, owner):
    _import(client, accountant, banks["wallet"], stmt(MAIN))
    _run(client, accountant)
    stray = next(r for r in client.get(f"/api/bank/rows?date_from={T}&date_to={T}", headers=accountant).json() if "DONATION" in r["description"])
    assert client.post(f"/api/bank/rows/{stray['id']}/not-ours", headers=accountant, json={"reason": ""}).status_code == 201  # blank = "No reason given" (owner decision)
    again = client.post(f"/api/bank/rows/{stray['id']}/not-ours", headers=accountant, json={"reason": "goodwill trust"})
    assert again.status_code == 409  # already decided
    ex = client.get(f"/api/bank/exceptions?date_from={T}&date_to={T}", headers=owner).json()
    assert ex["unmatched_credits"] == []


def test_manual_match_and_unmatch_need_reasons_and_leave_a_trail(client, banks, accountant, session_factory):
    _import(client, accountant, banks["wallet"], stmt([(T, "SOME LUMP SUM", "6000.00", "0")]))
    _run(client, accountant)
    # the 6,000 happens to equal the two PhonePe takings: the matcher suggests that, a person says no
    for sug in client.get("/api/bank/suggestions", headers=accountant).json():
        assert client.post(f"/api/bank/matches/{sug['match_id']}/reject", headers=accountant, json={"reason": "not PhonePe, it is a lump sum"}).status_code == 200
    exp = {e["label"]: e for e in client.get(f"/api/bank/expected?date_from={T}&date_to={T}", headers=accountant).json()}
    row = client.get(f"/api/bank/rows?date_from={T}&date_to={T}", headers=accountant).json()[0]
    assert client.post("/api/bank/matches/manual", headers=accountant, json={"expected_ids": [], "row_ids": [row["id"]], "reason": "x"}).status_code == 422
    too_much = client.post("/api/bank/matches/manual", headers=accountant, json={"expected_ids": [exp["DTP Card"]["id"]], "row_ids": [row["id"]], "reason": "lump"})
    assert too_much.status_code == 201  # 6,000 received against 10,000 expected: 4,000 recorded as charges/shortfall
    match_id = too_much.json()["id"]
    assert client.post(f"/api/bank/matches/{match_id}/unmatch", headers=accountant, json={"reason": "wrong pairing"}).status_code == 200
    assert client.post(f"/api/bank/matches/{match_id}/unmatch", headers=accountant, json={"reason": "again"}).status_code == 409
    paired = client.post("/api/bank/matches/manual", headers=accountant, json={"expected_ids": [exp["PTM"]["id"]], "row_ids": [row["id"]], "reason": "agreed by phone"})
    assert paired.status_code == 201
    # a bank line can only be in one live match
    assert client.post("/api/bank/matches/manual", headers=accountant, json={"expected_ids": [exp["DTP Card"]["id"]], "row_ids": [row["id"]], "reason": "again"}).status_code == 409
    more = client.post("/api/bank/matches/manual", headers=accountant, json={"expected_ids": [exp["PHONE PAY"]["id"]], "row_ids": [], "reason": "r"})
    assert more.status_code == 422
    for event in ("bank_match_manual", "bank_match_unmatched"):
        assert audit_events(session_factory, event), event


def test_an_owner_can_lock_a_match_and_then_nobody_else_can_undo_it(client, banks, accountant, owner):
    _import(client, accountant, banks["wallet"], stmt(MAIN[2:3]))  # the DTP line
    _run(client, accountant)
    live = [r for r in client.get(f"/api/bank/rows?date_from={T}&date_to={T}", headers=accountant).json()][0]
    assert live["match_status"] == "confirmed" and live["locked"] is False
    mid = live["match_id"]
    assert client.post(f"/api/bank/matches/{mid}/lock", headers=accountant, json={"locked": True}).status_code == 403  # owners only
    assert client.post(f"/api/bank/matches/{mid}/lock", headers=owner, json={"locked": True}).json()["locked"] is True
    refused = client.post(f"/api/bank/matches/{mid}/unmatch", headers=accountant, json={"reason": "oops"})
    assert refused.status_code == 409 and "locked" in refused.json()["error"]["message"]
    assert client.post(f"/api/bank/matches/{mid}/lock", headers=owner, json={"locked": False}).json()["locked"] is False
    assert client.post(f"/api/bank/matches/{mid}/unmatch", headers=accountant, json={"reason": "now it is open"}).status_code == 200


def test_money_that_reaches_the_bank_after_a_weekend_still_matches(client, banks, accountant):
    three_days_later = T + timedelta(days=3)  # inside the 4-day window: Friday takings, Monday credit
    _import(client, accountant, banks["wallet"], stmt([(three_days_later, "DTP FLEET CARD SETTLEMENT", "10000.00", "0")]))
    made = _run(client, accountant, T, three_days_later)
    assert made["auto"] == 1
    assert _days(client, accountant)["DTP Card"]["status"] == "matched"
    # ...but a credit more than the 4-day window after the takings is not matched by any rule
    late = T + timedelta(days=9)
    _import(client, accountant, banks["wallet"], stmt([(late, "DTP FLEET CARD SETTLEMENT", "10000.00", "0")], opening="0"), name="late.csv")
    assert _run(client, accountant, T, late)["auto"] == 0


def test_a_credit_the_bank_later_reverses_does_not_count_as_received(client, banks, accountant, session_factory):
    rows = [(T, "DTP FLEET CARD SETTLEMENT", "10000.00", "0"), (T + timedelta(days=2), "DTP SETTLEMENT REVERSAL", "0", "10000.00")]
    _import(client, accountant, banks["wallet"], stmt(rows))
    made = _run(client, accountant, T, T + timedelta(days=2))
    assert made["reversals"] == 1 and made["auto"] == 0
    days = _days(client, accountant)
    assert days["DTP Card"]["received"] == "0.00" and days["DTP Card"]["unmatched"] == "10000.00"
    assert audit_events(session_factory, "bank_reversal_paired")


def test_the_check_says_it_in_the_owners_words_and_follows_the_matching(client, banks, accountant, owner):
    _import(client, accountant, banks["wallet"], stmt(MAIN))
    _run(client, accountant)

    def paytm():
        client.post("/api/checks/run", headers=owner, json={"day": TODAY})
        rows = [c for c in client.get(f"/api/checks?day={TODAY}", headers=owner).json()["results"] if c["key"] == "bank.mode_expected_vs_received" and "PTM" in c["sentence"]]
        assert len(rows) == 1
        return rows[0]

    first = paytm()  # the 50,000 batch is only a suggestion so far: please confirm
    assert first["status"] == "warn" and "expected 50,000.00" in first["sentence"] and "waiting for someone to confirm" in first["sentence"]
    for s in client.get("/api/bank/suggestions", headers=accountant).json():
        client.post(f"/api/bank/matches/{s['match_id']}/confirm", headers=accountant)
    done = paytm()
    assert done["status"] == "pass" and done["expected"] == "50000.00" and done["actual"] == "50000.00"
    cash = [c for c in client.get(f"/api/checks?day={TODAY}", headers=owner).json()["results"] if c["key"] == "bank.mode_expected_vs_received" and "Cash deposits" in c["sentence"]][0]
    assert cash["status"] == "warn" and "not yet seen on the statement" in cash["sentence"]


def test_expected_receipts_follow_the_books_when_a_total_is_retyped(client, day, banks, accountant, manager):
    _run(client, accountant)
    modes = {r["name"]: r["tender_id"] for r in client.get(f"/api/shift-totals/{day['shifts'][0]['id']}", headers=manager).json()}
    client.put(f"/api/shift-totals/{day['shifts'][0]['id']}/{modes['Paytm']}", headers=manager, json={"amount": "31000.00"})
    _run(client, accountant)
    assert _days(client, accountant)["Paytm"]["expected"] == "51000.00"
