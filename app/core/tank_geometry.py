"""How high the fuel stands in a tank, for the picture of it.

An underground petrol-pump tank lies on its side, so litres do not rise evenly with height: the bottom and the top few centimetres hold
little, the middle holds the most. Two ways to find the height:

* the tank's own dip chart (dip in cm -> litres, as the oil company supplies it), read backwards by straight-line steps between its rows;
* otherwise the formula for a horizontal round tank with flat ends, which depends only on how full the tank is (a fraction of its
  capacity), not on its diameter.

Heights are returned as a fraction of the tank's height (0 = empty, 1 = full). This is for drawing only; stock figures never come from here.
"""

from math import acos, pi, sin
from typing import List, Optional, Tuple

DIP_CHART = "dip_chart"
ROUND_TANK = "round_tank"
APPROXIMATE = "approximate"


def volume_fraction_at_height(h: float) -> float:
    """Share of a horizontal round tank's volume below height h (h = height / diameter, 0..1)."""
    h = min(1.0, max(0.0, h))
    theta = 2 * acos(1 - 2 * h)
    return (theta - sin(theta)) / (2 * pi)


def height_fraction_for_volume(volume_fraction: float) -> float:
    """The inverse of volume_fraction_at_height, by halving the gap (the function only ever rises)."""
    f = min(1.0, max(0.0, volume_fraction))
    low, high = 0.0, 1.0
    for _ in range(60):
        mid = (low + high) / 2
        if volume_fraction_at_height(mid) < f:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def height_fraction_from_chart(points: List[Tuple[float, float]], litres: float) -> Optional[float]:
    """points = (dip_cm, litres) rows. Returns None when the chart cannot say (fewer than two rows, or no height)."""
    rows = sorted(points, key=lambda p: p[1])
    if len(rows) < 2 or rows[-1][0] <= 0:
        return None
    top_cm = max(p[0] for p in rows)
    if litres <= rows[0][1]:
        return max(0.0, rows[0][0]) / top_cm
    if litres >= rows[-1][1]:
        return 1.0
    for (cm_a, l_a), (cm_b, l_b) in zip(rows, rows[1:]):
        if l_a <= litres <= l_b:
            if l_b == l_a:
                return cm_b / top_cm
            return (cm_a + (cm_b - cm_a) * (litres - l_a) / (l_b - l_a)) / top_cm
    return None


def fill_height(stock: float, capacity: float, chart: Optional[List[Tuple[float, float]]] = None) -> Tuple[float, str]:
    """(height fraction, basis). basis says how it was worked out so the screen can label an approximate picture."""
    if chart:
        h = height_fraction_from_chart(chart, stock)
        if h is not None:
            return min(1.0, max(0.0, h)), DIP_CHART
    if capacity > 0:
        return height_fraction_for_volume(stock / capacity), ROUND_TANK
    return 0.0, APPROXIMATE
