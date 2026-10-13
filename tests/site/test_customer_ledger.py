"""The pure credit arithmetic: FIFO application of payments, ageing buckets, days to pay, statements.
Synthetic customers only."""

from datetime import date, timedelta
from decimal import Decimal

from app.services.customer_ledger import LedgerBill, LedgerPayment, apply_payments, bucket_of, statement_lines

D = Decimal
D0 = date(2026, 1, 1)


def bill(day, amount, ref="B", order=0, kind="sale", **kw):
    return LedgerBill(kind=kind, ref=ref, bill_date=D0 + timedelta(days=day), amount=D(amount), order=order, **kw)


def pay(day, amount):
    return LedgerPayment(D0 + timedelta(days=day), D(amount), "cash")


def test_a_payment_covering_several_bills_clears_the_oldest_first():
    bills = [bill(0, "100", "1", 0), bill(1, "200", "2", 1), bill(2, "300", "3", 2)]
    s = apply_payments(bills, [pay(10, "250")], D0 + timedelta(days=10))
    assert [(b.ref, b.paid, b.outstanding) for b in s.bills] == [("1", D("100"), D("0")), ("2", D("150"), D("50")), ("3", D("0"), D("300"))]
    assert s.balance == D("350") and s.total_billed == D("600") and s.total_paid == D("250") and s.unapplied == 0
    assert s.oldest_unpaid.ref == "2"  # bill 2 is only part paid, so it is still the oldest unpaid
    assert s.average_days_to_pay == D("10.0")  # only bill 1 is fully paid: paid on day 10, billed day 0


def test_a_part_payment_then_the_rest_gives_each_bill_its_own_days_to_pay():
    bills = [bill(0, "100", "1", 0), bill(1, "200", "2", 1), bill(2, "300", "3", 2)]
    s = apply_payments(bills, [pay(10, "250"), pay(20, "350")], D0 + timedelta(days=30))
    assert [b.outstanding for b in s.bills] == [0, 0, 0] and s.oldest_unpaid is None and s.balance == 0
    assert [b.days_to_pay for b in s.bills] == [10, 19, 18]  # bill 2 was cleared by the day-20 payment, bill 3 too
    assert s.average_days_to_pay == D("15.7")


def test_ageing_buckets_by_age_of_what_is_still_unpaid():
    bills = [bill(0, "100", "a", 0), bill(40, "200", "b", 1), bill(70, "300", "c", 2), bill(99, "400", "d", 3)]
    s = apply_payments(bills, [pay(100, "50")], D0 + timedelta(days=100))
    # 50 of bill a is paid first; ages at day 100: a=100 (90+), b=60 (31-60), c=30 (0-30), d=1 (0-30)
    assert s.buckets == {"0-30": D("700"), "31-60": D("200"), "61-90": D("0"), "90+": D("50")}
    assert sum(s.buckets.values()) == s.balance == D("1000") - D("50")
    assert (bucket_of(30), bucket_of(31), bucket_of(60), bucket_of(61), bucket_of(90), bucket_of(91)) == ("0-30", "31-60", "31-60", "61-90", "61-90", "90+")


def test_largest_amount_ever_owed_replays_bills_and_payments_in_order():
    bills = [bill(0, "500", "1", 0), bill(5, "700", "2", 1), bill(20, "100", "3", 2)]
    s = apply_payments(bills, [pay(10, "1000")], D0 + timedelta(days=30))
    assert s.largest_outstanding_ever == D("1200")  # 500 + 700 before the payment; afterwards 200, then 300
    assert s.balance == D("300")


def test_paying_in_advance_leaves_a_credit_not_a_negative_bill():
    s = apply_payments([bill(5, "100", "1", 0)], [pay(0, "300")], D0 + timedelta(days=6))
    assert s.bills[0].outstanding == 0 and s.unapplied == D("200") and s.balance == D("-200")
    assert s.bills[0].days_to_pay == 0  # paid before it was billed: no wait


def test_money_is_conserved_between_the_bills_and_the_balance():
    bills = [bill(i, str(100 + i * 7), str(i), i) for i in range(12)]
    pays = [pay(3, "250"), pay(9, "640.50"), pay(20, "100")]
    s = apply_payments(bills, pays, D0 + timedelta(days=40))
    assert sum(b.outstanding for b in s.bills) - s.unapplied == s.balance == sum(b.amount for b in bills) - sum(p.amount for p in pays)


def test_a_bowser_bill_counts_with_its_transport_and_carries_vehicle_and_slip():
    s = apply_payments([bill(0, "14750.00", "B1", 0, kind="bowser", vehicle_no="MH14XX0001", slip_no="S-1")], [], D0 + timedelta(days=5))
    b = s.bills[0]
    assert (b.kind, b.outstanding, b.age_days, b.vehicle_no, b.slip_no) == ("bowser", D("14750.00"), 5, "MH14XX0001", "S-1")


def test_statement_has_an_opening_balance_then_lines_with_a_running_balance():
    bills = [bill(0, "100", "1", 0), bill(10, "200", "2", 1, vehicle_no="V1", slip_no="S9"), bill(30, "50", "3", 2)]
    pays = [pay(5, "40"), pay(12, "100")]
    opening, lines, closing = statement_lines(bills, pays, D0 + timedelta(days=8), D0 + timedelta(days=20))
    assert opening == D("60")  # 100 billed - 40 paid before the 9th
    assert [(l.document, l.debit, l.credit, l.balance) for l in lines] == [
        ("Bill 2", D("200"), D("0"), D("260")), ("Payment received", D("0"), D("100"), D("160"))]
    assert (lines[0].vehicle_no, lines[0].slip_no) == ("V1", "S9")
    assert closing == D("160")  # the day-30 bill is outside the range


def test_a_customer_with_nothing_has_a_zero_summary():
    s = apply_payments([], [], D0)
    assert (s.balance, s.largest_outstanding_ever, s.average_days_to_pay, s.oldest_unpaid) == (0, 0, None, None)
