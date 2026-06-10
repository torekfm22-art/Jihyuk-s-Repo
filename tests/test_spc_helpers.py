"""SPC 판정 테스트용 분석 결과 빌더."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.spc.statistics import (
    CapabilityResult,
    NormalityResult,
    SpcAnalysisResult,
    SpcAnalyzer,
)


def _capability_from_indices(
    cp: float,
    cpk: float,
    usl: float = 10.5,
    lsl: float = 9.5,
) -> CapabilityResult:
    mean = (usl + lsl) / 2
    std_w = (usl - lsl) / (6 * cp) if cp > 0 else 0.1
    std_o = std_w
    cpu = (usl - mean) / (3 * std_w)
    cpl = (mean - lsl) / (3 * std_w)
    return CapabilityResult(
        usl=usl,
        lsl=lsl,
        mean=mean,
        std_within=std_w,
        std_overall=std_o,
        cp=cp,
        cpk=cpk,
        pp=cp,
        ppk=cpk,
        cpu=cpu,
        cpl=cpl,
        ppm_est=0.0,
    )


def _stable_subgroups(n_subgroups: int = 25, subgroup_size: int = 5) -> np.ndarray:
    """관리한계 내 안정적인 subgroup 데이터."""
    rng = np.random.default_rng(99)
    return rng.normal(10.0, 0.02, (n_subgroups, subgroup_size))


def build_stable_xbar_r(
    n_subgroups: int = 25,
    subgroup_size: int = 5,
    cp: float = 1.5,
    cpk: float = 1.5,
    is_normal: bool = True,
    r_unstable: bool = False,
) -> SpcAnalysisResult:
    """X-bar R 분석 결과 모의 생성."""
    subgroups = _stable_subgroups(n_subgroups, subgroup_size)
    analyzer = SpcAnalyzer()
    limits = analyzer.xbar_r_limits(subgroups)
    xbar = subgroups.mean(axis=1)
    r_vals = subgroups.max(axis=1) - subgroups.min(axis=1)

    if r_unstable:
        r_vals[-1] = limits.r_limits["UCL"] * 1.5

    subgroup_df = pd.DataFrame({
        "subgroup": np.arange(1, n_subgroups + 1),
        "Xbar": xbar,
        "R": r_vals,
    })

    ooc = [
        int(i + 1)
        for i, v in enumerate(xbar)
        if v > limits.xbar_limits["UCL"] or v < limits.xbar_limits["LCL"]
    ]

    norm = NormalityResult(
        "Shapiro-Wilk", 0.98, 0.15 if is_normal else 0.01, is_normal, 0.05,
        n_subgroups * subgroup_size,
    )
    cap = _capability_from_indices(cp, cpk)

    return SpcAnalysisResult(
        chart_type="xbar_r",
        normality=norm,
        control_limits=limits,
        capability=cap,
        subgroup_stats=subgroup_df,
        out_of_control_points=ooc,
    )


def build_stable_xbar_s(
    cp: float = 1.5,
    cpk: float = 1.5,
    is_normal: bool = True,
) -> SpcAnalysisResult:
    """X-bar S 안정 결과 (패턴 오탐 없음)."""
    subgroups = _stable_subgroups()
    analyzer = SpcAnalyzer()
    limits = analyzer.xbar_s_limits(subgroups)
    xbar = np.full(len(subgroups), limits.center_line)
    s_vals = subgroups.std(axis=1, ddof=1)
    subgroup_df = pd.DataFrame({
        "subgroup": np.arange(1, len(xbar) + 1),
        "Xbar": xbar,
        "S": s_vals,
    })
    norm = NormalityResult("Shapiro-Wilk", 0.98, 0.15 if is_normal else 0.01, is_normal, 0.05, 125)
    cap = _capability_from_indices(cp, cpk)
    return SpcAnalysisResult(
        chart_type="xbar_s",
        normality=norm,
        control_limits=limits,
        capability=cap,
        subgroup_stats=subgroup_df,
        out_of_control_points=[],
    )
