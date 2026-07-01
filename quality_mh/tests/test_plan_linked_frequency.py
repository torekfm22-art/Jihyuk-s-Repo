"""생산계획 연동 발생빈도 단위 테스트."""
from __future__ import annotations

import pytest

from quality_mh.plan_linked_frequency import (
    calc_average_ratio,
    calc_fg_style_plan_linked_frequency,
    calc_inspection_production_ratio,
    calc_product_inspection_shares,
    calc_simple_plan_linked_frequency,
)


class TestPlanLinkedFrequency:
    def test_simple_plan_linked(self):
        freq, factors, _ = calc_simple_plan_linked_frequency(46157, 816369, 381217.5)
        assert factors["ref_ratio"] == pytest.approx(46157 / 816369, rel=1e-4)
        assert freq == pytest.approx(factors["ref_ratio"] * 381217.5, rel=1e-3)

    def test_product_shares(self):
        shares = calc_product_inspection_shares({
            "리어램프": 46157,
            "헤드램프": 701765,
        })
        total = sum(shares.values())
        assert total == pytest.approx(1.0)
        assert shares["헤드램프"] > shares["리어램프"]

    def test_monthly_ratio_average(self):
        ratios = calc_inspection_production_ratio(
            [1000, 2000, 3000] + [0.0] * 9,
            [10000, 20000, 30000] + [0.0] * 9,
        )
        avg = calc_average_ratio(ratios, use_months=3)
        assert avg == pytest.approx(0.1, rel=1e-3)

    def test_fg_style_forecast(self):
        prior_by_product = {
            "리어램프": [3000.0] * 12,
            "헤드램프": [20000.0] * 12,
        }
        prior_prod = [50000.0] * 12
        forecast_prod = [40000.0] * 12
        freq, factors, log = calc_fg_style_plan_linked_frequency(
            prior_monthly_inspection_by_product=prior_by_product,
            prior_monthly_production=prior_prod,
            forecast_monthly_production=forecast_prod,
            ratio_months=12,
        )
        # prior ratio = 23000/50000 = 0.46 per month
        assert factors["avg_inspection_ratio"] == pytest.approx(0.46, rel=1e-2)
        assert freq == pytest.approx(0.46 * 40000 * 12, rel=1e-2)
        assert any("연간 발생빈도" in line for line in log)
