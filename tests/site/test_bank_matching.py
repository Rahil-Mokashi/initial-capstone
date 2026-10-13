"""The deterministic matcher: exact reference, amount + date window, batch settlement, charges deducted,
T+1 / weekend delay, reversal, and that the same inputs always give the same answer. Synthetic data only."""

import random
from datetime import date, timedelta
from decimal import Decimal

from app.services.bank_matching import Expected, Line, find_reversals, propose, window_for

D = Decimal
FRI = date(2026, 10, 9)  # a Friday
MON = FRI + timedelta(days=3)


def exp(id_, amount, day=FRI, window=4, ref=None, accounts=None):
    a, b = window_for(day, window)
    return Expected(id_, D(amount), a, b, ref, accounts=set(accounts or ()))


def line(id_, credit, day=FRI, desc="UPI CREDIT", ref=None, account="A", debit="0"):
    return Line(id_, day, D(credit), D(debit), desc, ref, account)


def only(proposals):
    assert len(proposals) == 1, proposals
    return proposals[0]


def test_same_reference_matches_by_itself_even_when_the_amount_is_a_bit_less():
    p = only(propose([exp("e1", "1000", ref="412345678901")], [line("r1", "985", desc="UPI/412345678901/PAYTM SETTLEMENT")]))
    assert (p.kind, p.auto, p.charges, p.line_ids) == ("reference", True, D("15"), ["r1"])


def test_same_reference_with_the_wrong_amount_is_only_a_suggestion():
    p = only(propose([exp("e1", "1000", ref="412345678901")], [line("r1", "900", desc="UPI/412345678901")]))
    assert p.kind == "reference" and p.auto is False and "amount differs" in p.note


def test_exactly_one_amount_inside_the_window_is_matched_without_a_person():
    p = only(propose([exp("e1", "4147.60")], [line("r1", "4147.60", day=FRI + timedelta(days=1))]))
    assert (p.kind, p.auto, p.charges) == ("amount_date", True, D("0"))


def test_a_friday_takings_credited_on_monday_still_match_and_wednesday_is_too_late():
    assert only(propose([exp("e1", "2000")], [line("r1", "2000", day=MON)])).auto is True  # T+1 over the weekend
    assert propose([exp("e1", "2000")], [line("r1", "2000", day=FRI + timedelta(days=6))]) == []  # outside the window
    assert propose([exp("e1", "2000")], [line("r1", "2000", day=FRI - timedelta(days=1))]) == []  # before it was taken


def test_two_equal_payments_and_one_bank_line_is_a_suggestion_not_a_guess():
    p = only(propose([exp("e1", "500", day=FRI), exp("e2", "500", day=FRI + timedelta(days=1))], [line("r1", "500", day=FRI + timedelta(days=1))]))
    assert p.auto is False and "more than one" in p.note
    assert p.expected_ids == ["e2"] or p.expected_ids == ["e1"]


def test_a_charge_deducted_before_settlement_is_a_suggestion_with_the_charge_shown():
    p = only(propose([exp("e1", "10000")], [line("r1", "9830")]))
    assert p.auto is False and p.charges == D("170") and "charge" in p.note
    assert propose([exp("e1", "10000")], [line("r1", "9000")]) == []  # 10% short is not a bank charge


def test_batch_settlement_several_days_in_one_credit():
    exps = [exp("e1", "1000", day=FRI), exp("e2", "2000", day=FRI + timedelta(days=1)), exp("e3", "3000", day=FRI + timedelta(days=2))]
    p = only(propose(exps, [line("r1", "6000", day=MON, desc="PAYTM SETTLEMENT BATCH")]))
    assert p.kind == "many_to_one" and sorted(p.expected_ids) == ["e1", "e2", "e3"] and p.auto is False and p.charges == 0


def test_batch_settlement_with_a_charge():
    exps = [exp("e1", "1000"), exp("e2", "2000"), exp("e3", "3000")]
    p = only(propose(exps, [line("r1", "5900", day=MON)]))
    assert p.kind == "many_to_one" and p.charges == D("100")


def test_one_payment_that_arrives_in_two_pieces():
    p = only(propose([exp("e1", "5000")], [line("r1", "2000"), line("r2", "3000", day=MON)]))
    assert p.kind == "one_to_many" and sorted(p.line_ids) == ["r1", "r2"] and p.charges == 0


def test_a_payment_may_only_land_in_the_accounts_that_take_its_mode():
    assert propose([exp("e1", "700", accounts=["A"])], [line("r1", "700", account="B")]) == []
    assert only(propose([exp("e1", "700", accounts=["A"])], [line("r1", "700", account="A")])).auto is True


def test_nothing_in_common_means_no_proposal_and_nothing_is_forced():
    assert propose([exp("e1", "1234.56")], [line("r1", "999.00"), line("r2", "5.00")]) == []
    assert propose([], [line("r1", "100")]) == [] and propose([exp("e1", "100")], []) == []


def test_each_bank_line_and_each_payment_is_used_at_most_once():
    exps = [exp("e1", "300"), exp("e2", "300", day=FRI + timedelta(days=2))]
    props = propose(exps, [line("r1", "300"), line("r2", "300", day=FRI + timedelta(days=2))])
    used_e = [i for p in props for i in p.expected_ids]
    used_r = [i for p in props for i in p.line_ids]
    assert len(used_e) == len(set(used_e)) and len(used_r) == len(set(used_r))


def test_the_answer_does_not_depend_on_the_order_of_the_inputs():
    exps = [exp(f"e{i}", str(100 * i), day=FRI + timedelta(days=i % 3)) for i in range(1, 8)]
    rows = [line(f"r{i}", str(100 * i), day=FRI + timedelta(days=i % 3 + 1)) for i in range(1, 8)]
    base = [(p.kind, tuple(p.expected_ids), tuple(p.line_ids), p.auto) for p in propose(exps, rows)]
    for seed in range(5):
        a, b = exps[:], rows[:]
        random.Random(seed).shuffle(a)
        random.Random(seed + 9).shuffle(b)
        assert [(p.kind, tuple(p.expected_ids), tuple(p.line_ids), p.auto) for p in propose(a, b)] == base


def test_a_reversal_is_paired_with_the_credit_it_undoes():
    rows = [line("c1", "1000", day=FRI), line("d1", "0", day=FRI + timedelta(days=4), desc="UPI REVERSAL 412345678901", debit="1000"),
            line("c2", "250", day=FRI), line("d2", "0", day=FRI + timedelta(days=1), desc="ATM WITHDRAWAL", debit="250")]
    assert find_reversals(rows) == [("c1", "d1")]  # the plain 250 debit is not a reversal: no such word, no shared reference


def test_a_debit_with_the_same_reference_is_a_reversal_too():
    rows = [line("c1", "800", desc="UPI/412345678901/X", ref="412345678901"), line("d1", "0", day=FRI + timedelta(days=2), desc="DR", ref="412345678901", debit="800")]
    assert find_reversals(rows) == [("c1", "d1")]
