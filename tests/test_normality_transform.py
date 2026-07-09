"""Box-Cox · Johnson 변환 및 변환 후 공정능력 테스트."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from src.spc.normality_transform import (
    resolve_normality_transform,
    try_box_cox_transform,
    try_johnson_transform,
)
from src.spc.statistics import SpcAnalyzer


def _lognormal_data(n: int = 125, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.lognormal(mean=2.2, sigma=0.35, size=n)


class TestBoxCoxTransform:
    def test_lognormal_may_normalize(self):
        data = _lognormal_data()
        usl, lsl = float(np.percentile(data, 99)), float(np.percentile(data, 1))
        result = try_box_cox_transform(data, usl, lsl)
        assert result is not None
        if result.applied:
            assert result.normality_after is not None
            assert result.normality_after.is_normal
            assert result.capability is not None
            assert result.capability.cpk > 0


class TestJohnsonTransform:
    def test_johnson_runs_on_skewed_data(self):
        data = _lognormal_data()
        usl, lsl = float(np.percentile(data, 99.5)), float(np.percentile(data, 0.5))
        result = try_johnson_transform(data, usl, lsl)
        assert result is not None
        assert result.method == "johnson_su"
        assert result.transformed_data is not None
        assert len(result.transformed_data) == len(data)


class TestResolvePipeline:
    def test_resolve_tries_boxcox_first(self):
        data = _lognormal_data()
        usl, lsl = float(np.max(data) * 1.05), float(np.min(data) * 0.95)
        result = resolve_normality_transform(
            data, usl, lsl, chart_type="xbar_s", subgroup_size=5
        )
        assert result.method in ("box_cox", "johnson_su", "none")
        if result.applied:
            assert result.capability is not None
            assert result.normality_after is not None
            assert result.normality_after.is_normal

    def test_normal_data_no_transform(self):
        rng = np.random.default_rng(1)
        data = rng.normal(10.0, 0.5, 80)
        result = resolve_normality_transform(data, 12.0, 8.0)
        assert result.applied is False
        assert result.method == "none"

    def test_one_sided_upper_only_does_not_crash(self):
        data = _lognormal_data()
        usl = float(np.max(data) * 1.05)
        result = resolve_normality_transform(data, usl, None, chart_type="imr", subgroup_size=1)
        assert result is not None
        assert result.method in ("box_cox", "johnson_su", "none")

    def test_one_sided_lower_only_does_not_crash(self):
        data = _lognormal_data()
        lsl = float(np.min(data) * 0.95)
        result = resolve_normality_transform(data, None, lsl, chart_type="imr", subgroup_size=1)
        assert result is not None
        assert result.method in ("box_cox", "johnson_su", "none")

    def test_attempts_recorded_on_non_normal(self):
        data = _lognormal_data()
        usl, lsl = float(np.max(data) * 1.05), float(np.min(data) * 0.95)
        result = resolve_normality_transform(data, usl, lsl, chart_type="xbar_s", subgroup_size=5)
        assert len(result.attempts) == 2
        methods = {a["method"] for a in result.attempts}
        assert methods == {"box_cox", "johnson_su"}
        if result.applied:
            assert sum(1 for a in result.attempts if a.get("selected")) == 1
