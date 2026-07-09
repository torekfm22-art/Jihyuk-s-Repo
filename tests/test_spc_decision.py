"""SPC 판정 엔진 시나리오 테스트 (9건)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.spc.decision_service import SpcDecisionInput, SpcDecisionService
from src.spc.minitab_charts import ChartPaths
from src.spc.policy_config import SpcPolicyConfig
from src.spc.report_audit_engine import audit_report_completeness
from tests.test_spc_helpers import build_stable_xbar_r, build_stable_xbar_s


@pytest.fixture
def policy() -> SpcPolicyConfig:
    return SpcPolicyConfig(
        subgroup_min_groups=25,
        cp_cpk_threshold=1.33,
        pp_ppk_threshold=1.67,
        strict_company_mode=True,
        advanced_spc_mode=False,
        enable_customer_exception_rule=True,
    )


@pytest.fixture
def service(policy: SpcPolicyConfig) -> SpcDecisionService:
    return SpcDecisionService(policy)


@pytest.fixture
def stable_raw() -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.normal(10.0, 0.05, 125)


@pytest.fixture
def full_charts(tmp_path: Path) -> ChartPaths:
    for name in ("hist.png", "raw.png", "prob.png", "ctrl.png"):
        (tmp_path / name).write_bytes(b"png")
    return ChartPaths(
        histogram=tmp_path / "hist.png",
        raw_chart=tmp_path / "raw.png",
        prob_plot=tmp_path / "prob.png",
        control_chart=tmp_path / "ctrl.png",
    )


def _evaluate(service, analysis, raw, **kwargs):
    return service.evaluate(
        SpcDecisionInput(
            analysis=analysis,
            raw_data=raw,
            usl=10.5,
            lsl=9.5,
            subgroup_size=5,
            **kwargs,
        )
    )


class TestScenario1StableCapable:
    """양산, 안정, 정규, Cp/Cpk 충분."""

    def test_mass_production_capable(self, service, stable_raw, full_charts):
        analysis = build_stable_xbar_s(cp=1.5, cpk=1.5, is_normal=True)
        decision = _evaluate(
            service, analysis, stable_raw,
            stage="mass_production", charts=full_charts,
        )
        assert decision.compliance.can_deploy_control_chart == "possible"
        assert decision.capability.capability_status == "sufficient"
        assert decision.capability.improvement_focus == "maintain_monitor"
        assert "유지" in decision.capability.recommendation or "모니터링" in decision.capability.recommendation


class TestScenario2Centering:
    """양산, 안정, Cp 충분, Cpk 부족."""

    def test_centering_recommended(self, service, stable_raw, full_charts):
        analysis = build_stable_xbar_s(cp=1.5, cpk=1.0, is_normal=True)
        decision = _evaluate(
            service, analysis, stable_raw,
            stage="mass_production", charts=full_charts,
        )
        assert decision.capability.improvement_focus == "centering"
        assert "중심" in decision.capability.recommendation
        assert decision.capability.improvement_focus != "variation"


class TestScenario3Variation:
    """양산, 안정, Cp/Cpk 둘 다 부족."""

    def test_variation_recommended(self, service, stable_raw, full_charts):
        analysis = build_stable_xbar_s(cp=1.0, cpk=0.9, is_normal=True)
        decision = _evaluate(
            service, analysis, stable_raw,
            stage="mass_production", charts=full_charts,
        )
        assert decision.capability.improvement_focus == "variation"
        assert "산포" in decision.capability.recommendation


class TestScenario4RChartUnstable:
    """양산, R 관리도 불안정."""

    def test_mean_chart_deferred(self, service, stable_raw, full_charts):
        analysis = build_stable_xbar_r(cp=1.5, cpk=1.5, r_unstable=True)
        decision = _evaluate(
            service, analysis, stable_raw,
            stage="mass_production", charts=full_charts,
        )
        assert decision.control_chart.r_chart_status == "unstable"
        assert decision.control_chart.mean_chart_status == "deferred"
        assert decision.compliance.can_deploy_control_chart == "not_possible"
        assert decision.control_chart.status in ("deferred", "unstable")
        log_ids = [e.rule_id for e in decision.control_chart.decision_log]
        assert "R_CHART_FIRST" in log_ids


class TestScenario5DevelopmentStage:
    """개발단계, Ppk 부족."""

    def test_pp_ppk_applied(self, service, stable_raw, full_charts):
        analysis = build_stable_xbar_s(cp=1.5, cpk=1.2, is_normal=True)
        analysis.capability.pp = 1.5
        analysis.capability.ppk = 1.2
        decision = _evaluate(
            service, analysis, stable_raw,
            stage="development", charts=full_charts,
        )
        assert decision.capability.metric_basis == "PpPpk"
        assert decision.capability.primary_kpi == "Ppk"
        log_msgs = " ".join(e.message for e in decision.control_chart.decision_log)
        assert "Pp/Ppk" in log_msgs or "PpPpk" in log_msgs


class TestScenario6StrictNonNormal:
    """strict_company_mode=True, 비정규."""

    def test_requires_recollection(self, service, stable_raw, full_charts):
        analysis = build_stable_xbar_s(cp=1.5, cpk=1.5, is_normal=False)
        decision = _evaluate(
            service, analysis, stable_raw,
            stage="mass_production", charts=full_charts,
        )
        assert decision.compliance.requires_recollection is True
        assert "재수집" in decision.normality.handling_recommendation or "재분석" in decision.normality.handling_recommendation


class TestScenario7SpecialCharacteristic:
    """특별특성, 공정능력 부족."""

    def test_enhanced_controls(self, service, stable_raw, full_charts):
        analysis = build_stable_xbar_s(cp=1.0, cpk=0.9, is_normal=True)
        decision = _evaluate(
            service, analysis, stable_raw,
            stage="mass_production",
            special_characteristic=True,
            charts=full_charts,
        )
        assert decision.compliance.requires_containment is True
        assert decision.compliance.requires_100pct_inspection is True
        assert decision.compliance.requires_control_plan_review is True


class TestScenario8CustomerException:
    """고객 예외: Cp 충분, Cpk 부족."""

    def test_exceptional_acceptance(self, service, stable_raw, full_charts):
        analysis = build_stable_xbar_s(cp=1.5, cpk=1.0, is_normal=True)
        decision = _evaluate(
            service, analysis, stable_raw,
            stage="mass_production",
            customer_exception_mode=True,
            customer_exception_reason="고객 인지 규격 오류 현품 맞춤",
            charts=full_charts,
        )
        assert decision.compliance.can_deploy_control_chart == "exceptional"
        assert decision.compliance.requires_customer_exception_review is True
        assert "예외" in decision.expert_commentary.executive_summary or "exception" in decision.expert_commentary.executive_summary.lower()


class TestScenario9ReportCompleteness:
    """리포트 완전성 일부 누락."""

    def test_completeness_missing(self, stable_raw):
        analysis = build_stable_xbar_s()
        audit = audit_report_completeness(charts=None, analysis=analysis)
        assert audit.completeness_ok is False
        assert "histogram" in audit.missing_items
        assert "control chart" in audit.missing_items

    def test_completeness_ok(self, stable_raw, full_charts):
        analysis = build_stable_xbar_s()
        audit = audit_report_completeness(charts=full_charts, analysis=analysis)
        assert audit.completeness_ok is True
        assert audit.missing_items == []
