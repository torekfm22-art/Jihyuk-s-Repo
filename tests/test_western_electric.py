"""Western Electric Rules 및 안정성 기반 판정 테스트."""
from __future__ import annotations

import numpy as np
import pytest

from src.spc.decision_service import SpcDecisionInput, SpcDecisionService
from src.spc.policy_config import SpcPolicyConfig
from src.spc.western_electric import detect_western_electric_rules
from tests.test_spc_helpers import build_stable_xbar_r, build_stable_xbar_s


@pytest.fixture
def policy() -> SpcPolicyConfig:
    return SpcPolicyConfig(
        subgroup_min_groups=25,
        cp_cpk_threshold=1.33,
        pp_ppk_threshold=1.67,
        run_rule_points=7,
        trend_rule_points=7,
    )


@pytest.fixture
def service(policy: SpcPolicyConfig) -> SpcDecisionService:
    return SpcDecisionService(policy)


class TestWesternElectricRules:
    def test_rule1_beyond_3sigma(self):
        cl, ucl, lcl = 10.0, 10.3, 9.7
        values = np.array([10.0, 10.01, 10.35, 10.0, 9.99])
        ids = [1, 2, 3, 4, 5]
        violations, patterns = detect_western_electric_rules(values, cl, ucl, lcl, ids)
        assert any(v.rule_id == "WE_R1" for v in violations)
        assert violations[0].affected_subgroups == [3]

    def test_rule4_run_same_side(self):
        cl, ucl, lcl = 10.0, 10.3, 9.7
        values = np.array([10.05, 10.06, 10.04, 10.07, 10.05, 10.06, 10.04])
        ids = list(range(1, 8))
        violations, _ = detect_western_electric_rules(values, cl, ucl, lcl, ids, run_points=7)
        assert any(v.rule_id == "WE_R4" for v in violations)

    def test_rule5_trend(self):
        cl, ucl, lcl = 10.0, 10.5, 9.5
        values = np.linspace(9.8, 10.2, 7)
        ids = list(range(1, 8))
        violations, _ = detect_western_electric_rules(values, cl, ucl, lcl, ids, trend_points=7)
        assert any(v.rule_id == "WE_R5" for v in violations)


class TestStabilityBasedCapability:
    def test_stable_mass_production_uses_cpk(self, service):
        raw = np.random.default_rng(1).normal(10.0, 0.02, 125)
        analysis = build_stable_xbar_s(cp=1.5, cpk=1.5, is_normal=True)
        decision = service.evaluate(
            SpcDecisionInput(
                analysis=analysis, raw_data=raw, usl=10.5, lsl=9.5,
                subgroup_size=5, stage="mass_production",
            )
        )
        assert decision.verdict_summary.process_stability == "Stable (In Control)"
        assert decision.capability.primary_kpi == "Cpk"
        assert decision.capability.cp_cpk_valid is True
        assert "Valid" in decision.verdict_summary.cp_cpk_validity

    def test_unstable_r_chart_uses_ppk(self, service):
        raw = np.random.default_rng(2).normal(10.0, 0.02, 125)
        analysis = build_stable_xbar_r(cp=1.5, cpk=1.5, r_unstable=True)
        decision = service.evaluate(
            SpcDecisionInput(
                analysis=analysis, raw_data=raw, usl=10.5, lsl=9.5,
                subgroup_size=5, stage="mass_production",
            )
        )
        assert decision.verdict_summary.process_stability == "Unstable (Out of Control)"
        assert decision.capability.primary_kpi == "Ppk"
        assert decision.capability.cp_cpk_valid is False
        assert "Invalid" in decision.verdict_summary.cp_cpk_validity
        assert "Level 1" in decision.capability.process_level

    def test_cpk_ppk_gap_recorded(self, service):
        raw = np.random.default_rng(3).normal(10.0, 0.02, 125)
        analysis = build_stable_xbar_s(cp=1.5, cpk=1.5, is_normal=True)
        analysis.capability.ppk = 1.2
        decision = service.evaluate(
            SpcDecisionInput(
                analysis=analysis, raw_data=raw, usl=10.5, lsl=9.5,
                subgroup_size=5, stage="mass_production",
            )
        )
        assert decision.capability.cpk_ppk_gap is not None
        assert decision.capability.cpk_ppk_gap > 0
