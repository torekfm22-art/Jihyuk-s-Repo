"""σ 구간선 유틸 테스트."""
from src.spc.chart_sigma_zones import iter_sigma_zone_lines, sigma_zone_widths


def test_sigma_zone_widths_asymmetric():
    up, lo = sigma_zone_widths(10.0, 13.0, 8.0)
    assert abs(up - 1.0) < 1e-9
    assert abs(lo - 2.0 / 3.0) < 1e-9


def test_sigma_zone_lines_symmetric():
    cl, ucl, lcl = 10.0, 13.0, 7.0
    ys = [y for y, _ in iter_sigma_zone_lines(cl, ucl, lcl)]
    assert 11.0 in ys
    assert 12.0 in ys
    assert 13.0 not in ys  # +3σ = UCL → 생략
    assert 9.0 in ys
    assert 8.0 in ys
    assert 7.0 not in ys  # -3σ = LCL → 생략


def test_sigma_zone_lines_one_sided_dispersion():
    cl, ucl, lcl = 0.5, 1.0, 0.0
    ys = [y for y, _ in iter_sigma_zone_lines(cl, ucl, lcl)]
    assert any(abs(y - (cl + (ucl - cl) / 3)) < 1e-9 for y in ys)
    assert any(abs(y - (cl - cl / 3)) < 1e-9 for y in ys)
