from app.core.tank_geometry import (
    APPROXIMATE, DIP_CHART, ROUND_TANK, fill_height, height_fraction_for_volume, height_fraction_from_chart, volume_fraction_at_height,
)


def test_a_half_full_round_tank_stands_at_half_height_and_the_ends_are_exact():
    assert abs(height_fraction_for_volume(0.5) - 0.5) < 1e-9
    assert height_fraction_for_volume(0) < 1e-9 and abs(height_fraction_for_volume(1) - 1) < 1e-9


def test_litres_do_not_rise_evenly_with_height():
    # a quarter of the height holds well under a quarter of the fuel; the formula and its inverse agree
    assert volume_fraction_at_height(0.25) < 0.25
    assert abs(volume_fraction_at_height(0.25) - 0.1955) < 0.001
    for f in (0.05, 0.2, 0.5, 0.8, 0.95):
        assert abs(volume_fraction_at_height(height_fraction_for_volume(f)) - f) < 1e-9
    assert height_fraction_for_volume(0.2) > 0.2  # 20% of the fuel stands higher than 20% of the height


def test_the_dip_chart_wins_when_there_is_one_and_is_read_between_its_rows():
    chart = [(0.0, 0.0), (50.0, 5000.0), (100.0, 20000.0)]
    h, basis = fill_height(12500.0, 20000.0, chart)
    assert basis == DIP_CHART and abs(h - 0.75) < 1e-9  # halfway between 5000 and 20000 litres is 75 cm of 100
    assert fill_height(30000.0, 20000.0, chart) == (1.0, DIP_CHART)
    assert fill_height(0.0, 20000.0, chart)[0] == 0.0


def test_without_a_chart_the_round_tank_formula_is_used_and_without_capacity_it_is_approximate():
    h, basis = fill_height(10000.0, 20000.0, None)
    assert basis == ROUND_TANK and abs(h - 0.5) < 1e-9
    assert fill_height(5.0, 0.0, [])[1] == APPROXIMATE
    assert fill_height(5.0, 20000.0, [(10.0, 100.0)])[1] == ROUND_TANK  # one row is not a chart
    assert height_fraction_from_chart([(10.0, 1.0)], 1.0) is None
