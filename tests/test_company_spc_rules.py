"""관리도 해석 9 Rule 테스트 — config/control_chart_rules.json 기준."""
from __future__ import annotations

import numpy as np
import pytest

from src.spc.spc_interpreter import SpcInterpretConfig, interpret_control_chart

CL, UCL, LCL = 10.0, 10.3, 9.7
USL, LSL = 10.5, 9.5
IDS = list(range(1, 26))


@pytest.fixture
def cfg() -> SpcInterpretConfig:
    return SpcInterpretConfig()


class TestInControl:
    def test_short_series_in_control(self, cfg):
        """14점 미만·15연속 ±1σ 미만 데이터 — 9 Rule 미발생."""
        sigma = (UCL - CL) / 3
        pattern = np.array([0.45, -0.45, 0.40, -0.40, 0.42, -0.42] * 2)
        values = CL + sigma * pattern
        ids = list(range(1, len(values) + 1))
        result = interpret_control_chart(values, CL, UCL, LCL, ids, config=cfg)
        assert result.status == "관리상태"
        assert len(result.detected_rules) == 0


class TestNineRules:
    def test_spec_limit_out(self, cfg):
        values = np.full(25, CL)
        values[3] = USL + 0.1
        result = interpret_control_chart(
            values, CL, UCL, LCL, IDS, usl=USL, lsl=LSL, config=cfg
        )
        assert result.status == "비관리상태"
        assert any(r.rule_id == "SPEC_LIMIT_OUT" for r in result.detected_rules)

    def test_control_limit_out(self, cfg):
        values = np.full(25, CL)
        values[5] = UCL + 0.05
        result = interpret_control_chart(values, CL, UCL, LCL, IDS, config=cfg)
        assert result.status == "비관리상태"
        assert any(r.rule_id == "CONTROL_LIMIT_OUT" for r in result.detected_rules)

    def test_oscillation(self, cfg):
        values = np.array([CL + (0.06 if i % 2 == 0 else -0.06) for i in range(20)])
        ids = list(range(1, 21))
        result = interpret_control_chart(values, CL, UCL, LCL, ids, config=cfg)
        assert result.status == "비관리상태"
        assert any(r.rule_id == "OSCILLATION" for r in result.detected_rules)

    def test_zone_rule_1(self, cfg):
        sigma = (UCL - CL) / 3
        two_sigma = CL + 2 * sigma + 0.001
        values = np.array([CL, two_sigma, two_sigma] + [CL] * 22)
        result = interpret_control_chart(values, CL, UCL, LCL, IDS, config=cfg)
        assert result.status == "비관리상태"
        assert any(r.rule_id == "ZONE_RULE_1" for r in result.detected_rules)

    def test_hugging(self, cfg):
        sigma = (UCL - CL) / 3
        values = np.array([CL + sigma * 0.05] * 20)
        ids = list(range(1, 21))
        result = interpret_control_chart(values, CL, UCL, LCL, ids, config=cfg)
        assert result.status == "비관리상태"
        assert any(r.rule_id == "HUGGING" for r in result.detected_rules)

    def test_shift_seven_points(self, cfg):
        values = np.array([10.05] * 7 + [10.0] * 18)
        result = interpret_control_chart(values, CL, UCL, LCL, IDS, config=cfg)
        assert result.status == "비관리상태"
        assert any(r.rule_id == "SHIFT" for r in result.detected_rules)

    def test_shift_six_points_not_detected(self, cfg):
        values = np.array([10.05] * 6 + [10.0] * 19)
        result = interpret_control_chart(values, CL, UCL, LCL, IDS, config=cfg)
        assert not any(r.rule_id == "SHIFT" for r in result.detected_rules)

    def test_trend_six_points(self, cfg):
        values = np.concatenate([np.linspace(9.90, 10.08, 6), np.full(19, 10.0)])
        result = interpret_control_chart(values, CL, UCL, LCL, IDS, config=cfg)
        assert result.status == "비관리상태"
        assert any(r.rule_id == "TREND" for r in result.detected_rules)

    def test_zone_rule_2(self, cfg):
        sigma = (UCL - CL) / 3
        one_sigma = CL + sigma + 0.001
        values = np.array([one_sigma] * 4 + [CL] + [CL] * 20)
        result = interpret_control_chart(values, CL, UCL, LCL, IDS, config=cfg)
        assert result.status == "비관리상태"
        assert any(r.rule_id == "ZONE_RULE_2" for r in result.detected_rules)

    def test_excess_dispersion(self, cfg):
        sigma = (UCL - CL) / 3
        outside = CL + sigma * 1.5
        values = np.array([outside] * 8 + [CL] * 17)
        result = interpret_control_chart(values, CL, UCL, LCL, IDS, config=cfg)
        assert result.status == "비관리상태"
        assert any(r.rule_id == "EXCESS_DISPERSION" for r in result.detected_rules)


class TestRulePayload:
    def test_detected_rule_has_interpretation_and_values(self, cfg):
        values = np.full(25, CL)
        values[0] = UCL + 0.1
        result = interpret_control_chart(values, CL, UCL, LCL, IDS, config=cfg)
        rule = result.detected_rules[0]
        assert rule.interpretation_meaning
        assert rule.matched_points == [1]
        assert len(rule.matched_values) == 1
        d = rule.to_dict()
        assert "interpretationMeaning" in d
        assert "matchedValues" in d


class TestDispersionDeferred:
    def test_dispersion_abnormal_flag(self, cfg):
        values = np.full(25, CL)
        result = interpret_control_chart(
            values, CL, UCL, LCL, IDS, config=cfg, dispersion_abnormal=True
        )
        assert result.mean_chart_deferred is True
