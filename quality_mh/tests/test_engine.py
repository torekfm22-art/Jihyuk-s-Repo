"""pytest 기반 계산 엔진 단위 테스트."""
from __future__ import annotations

import pytest

from quality_mh.calculation_engine import (
    apply_allowance,
    calculate_quantitative_record,
    calculate_standard_mh_excel_style,
    calculate_standard_work_time_excel_style,
    round_headcount_standard_rule,
)
from quality_mh.frequency_engine import (
    calculate_frequency_by_task_rule,
    calculate_frequency_periodic_excel_style,
    calculate_frequency_plan_linked_excel_style,
    calculate_frequency_weighted_average_excel_style,
)
from quality_mh.sample_data import (
    scenario_1_weighted_avg,
    scenario_2_plan_linked,
    scenario_3_periodic,
)
from quality_mh.validation import ValidationError, validate_record


class TestFrequencyEngine:
    def test_weighted_average(self):
        freq, factors, log = calculate_frequency_weighted_average_excel_style(120, 100, 80)
        # (120×5 + 100×3 + 80×2) / 10 = 106.0
        assert freq == pytest.approx(106.0, rel=1e-3)
        assert factors["weighted_sum"] == pytest.approx(1060.0, rel=1e-3)
        assert any("106.0" in line for line in log)

    def test_plan_linked(self):
        freq, _, log = calculate_frequency_plan_linked_excel_style(0.02, 50000)
        assert freq == pytest.approx(1000.0, rel=1e-3)
        assert len(log) >= 3

    def test_periodic_weekly(self):
        freq, _, log = calculate_frequency_periodic_excel_style("주간", 2.0, working_weeks=4.0)
        assert freq == pytest.approx(8.0, rel=1e-3)
        assert any("8.0" in line for line in log)


class TestScenario1WeightedAvg:
    def test_full_pipeline(self):
        record, rule, freq_db = scenario_1_weighted_avg()
        validate_record(record, rule, freq_db)

        freq, method, _, _, _ = calculate_frequency_by_task_rule(rule, freq_db)
        assert freq == pytest.approx(106.0, rel=1e-3)

        std_time, unit_hr, _ = calculate_standard_work_time_excel_style(record.unit_time_min, freq)
        assert unit_hr == pytest.approx(0.5, rel=1e-3)
        assert std_time == pytest.approx(53.0, rel=1e-3)

        final_time, _ = apply_allowance(std_time, 0.10)
        assert final_time == pytest.approx(58.3, rel=1e-3)

        mh, md, _ = calculate_standard_mh_excel_style(final_time)
        assert mh == pytest.approx(0.2915, rel=1e-2)
        assert md == pytest.approx(0.02915, rel=1e-2)

        headcount, _ = round_headcount_standard_rule(mh)
        assert headcount == 1

        result = calculate_quantitative_record(record, rule, freq_db)
        assert result.final_frequency == pytest.approx(106.0, rel=1e-3)
        assert result.standard_work_time_hr == pytest.approx(53.0, rel=1e-3)
        assert result.final_work_time_hr == pytest.approx(58.3, rel=1e-3)
        assert result.standard_mh == pytest.approx(0.2915, rel=1e-2)
        assert result.standard_headcount == 1


class TestScenario2PlanLinked:
    def test_full_pipeline(self):
        record, rule, freq_db = scenario_2_plan_linked()
        validate_record(record, rule, freq_db)

        result = calculate_quantitative_record(record, rule, freq_db)
        assert result.final_frequency == pytest.approx(1000.0, rel=1e-3)
        assert result.standard_work_time_hr == pytest.approx(83.333, rel=1e-2)
        assert result.final_work_time_hr == pytest.approx(91.667, rel=1e-2)
        assert result.standard_mh == pytest.approx(0.458, rel=1e-2)
        assert result.standard_headcount == 1


class TestScenario3Periodic:
    def test_full_pipeline(self):
        record, rule, freq_db = scenario_3_periodic()
        validate_record(record, rule, freq_db)

        result = calculate_quantitative_record(record, rule, freq_db)
        assert result.final_frequency == pytest.approx(8.0, rel=1e-3)
        assert result.standard_work_time_hr == pytest.approx(8.0, rel=1e-3)
        assert result.final_work_time_hr == pytest.approx(8.8, rel=1e-3)
        assert result.standard_mh == pytest.approx(0.044, rel=1e-2)
        assert result.standard_headcount == 1


class TestValidation:
    def test_zero_unit_time_raises(self):
        record, rule, freq_db = scenario_1_weighted_avg()
        record.unit_time_min = 0
        with pytest.raises(ValidationError):
            validate_record(record, rule, freq_db)

    def test_negative_value_raises(self):
        record, rule, freq_db = scenario_1_weighted_avg()
        record.current_headcount = -1
        with pytest.raises(ValidationError):
            validate_record(record, rule, freq_db)
