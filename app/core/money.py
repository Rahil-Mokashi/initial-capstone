"""One place that decides how money is rounded.

Every monetary figure in this app is a Decimal (never a float - see
PROJECT_CONTEXT.md's Float-to-Numeric migration), which makes the
arithmetic exact. Exact is not the same as *settled*, though: multiplying
a litre quantity carrying three decimal places by a rate carrying two
produces a result with five, and something has to decide what the
two-decimal money value actually is.

Left alone, two separate things decide it, neither deliberately. Python's
Decimal context rounds with ROUND_HALF_EVEN ("banker's rounding", which
sends exact halves to the nearest *even* digit to avoid statistical bias
over many roundings). And the Numeric(10, 2) column applies its own
rounding again on the way into the database. Indian invoicing convention
is ROUND_HALF_UP - an exact half always rounds away from zero - so the
default is simply the wrong answer, and worse, it is a wrong answer that
differs by a paisa only sometimes, which is exactly the kind of variance
nobody can explain when a month of reconciliation totals disagree.

So: compute in full precision, then call money() at the point a figure
becomes a monetary amount that will be stored, displayed or compared.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Union

# Two decimal places: paise. Matches Numeric(10, 2) on every money column.
MONEY_QUANTUM = Decimal("0.01")

# Litres are tracked to three decimal places - a millilitre. Fuel
# dispensers report to that resolution, and rounding volumes to two would
# quietly lose stock on every single transaction.
VOLUME_QUANTUM = Decimal("0.001")

Numeric = Union[Decimal, int, str]


def _to_decimal(value: Numeric) -> Decimal:
    """Coerce to Decimal without ever routing through a float.

    Decimal(0.1) faithfully reproduces the binary float's error and gives
    0.1000000000000000055511151231257827; Decimal("0.1") gives a tenth.
    So a float is converted via its string representation, the same way
    Pydantic does it, rather than passed to Decimal() directly.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def money(value: Numeric) -> Decimal:
    """Settle a computed value into a monetary amount (2 dp, half-up)."""
    return _to_decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def volume(value: Numeric) -> Decimal:
    """Settle a computed value into a volume in litres (3 dp, half-up)."""
    return _to_decimal(value).quantize(VOLUME_QUANTUM, rounding=ROUND_HALF_UP)
