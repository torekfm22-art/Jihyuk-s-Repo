"""정규성 판정 — Shapiro vs QQ plot 일관성."""
from __future__ import annotations

import numpy as np

from src.spc.policy_config import SpcPolicyConfig
from src.spc.qqplot_assessment import assess_qq_plot
from src.spc.rule_engine import classify_normality_state
from src.spc.statistics import SpcAnalyzer


def test_constant_data_not_marked_non_normal():
    """산포 없음: p=1.0이어도 비정규 후속조치를 트리거하지 않음."""
    x = np.ones(25) * 5.0
    norm = SpcAnalyzer().test_normality(x)
    qq = assess_qq_plot(x)
    policy = SpcPolicyConfig()

    assert norm.p_value == 1.0
    assert norm.is_normal
    assert qq.state_hint == "undetermined"
    assert qq.fit_r2 is None

    state = classify_normality_state(norm, qq, policy)
    assert state == "undetermined"


def test_shapiro_normal_data_classified_normal():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 100)
    norm = SpcAnalyzer().test_normality(x)
    qq = assess_qq_plot(x)
    policy = SpcPolicyConfig()

    state = classify_normality_state(norm, qq, policy)
    assert state == "normal"
