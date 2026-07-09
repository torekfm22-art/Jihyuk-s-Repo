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


def _in_control_xbar(cl: float, ucl: float, lcl: float, n: int = 25) -> np.ndarray:
    """9 Rule 미발생 Xbar 시계열 (σ 배수 템플릿)."""
    sigma_u = (ucl - cl) / 3.0 if ucl != cl else 0.05
    sigma_l = (cl - lcl) / 3.0 if lcl != cl else 0.05
    template = [
        0.5, -0.5, 0.3, -0.3, 0.4, 1.4, -0.4, 0.2, -0.6, 0.5,
        -0.5, 0.4, -0.3, 0.5, 1.4, -0.5, 0.3, -0.4, 0.2, -0.5,
        0.4, -0.3, 0.5, -0.4, 0.3,
    ]
    if n != len(template):
        raise ValueError(f"in-control template supports n={len(template)}, got {n}")
    values = np.array([
        float(np.clip(cl + (sigma_u if t >= 0 else -sigma_l) * abs(t), lcl + 1e-9, ucl - 1e-9))
        for t in template
    ])
    return values


def _stable_subgroups(n_subgroups: int = 25, subgroup_size: int = 5) -> np.ndarray:
    """관리한계 내 subgroup 원시 데이터."""
    rng = np.random.default_rng(99)
    return rng.normal(10.0, 0.025, (n_subgroups, subgroup_size))


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
    xbar = _in_control_xbar(
        limits.xbar_limits["CL"],
        limits.xbar_limits["UCL"],
        limits.xbar_limits["LCL"],
        n_subgroups,
    )
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
    """X-bar S 안정 결과 (회사 표준 오탐 방지 — 자연스러운 Xbar 변동)."""
    subgroups = _stable_subgroups()
    analyzer = SpcAnalyzer()
    limits = analyzer.xbar_s_limits(subgroups)
    xbar = _in_control_xbar(
        limits.xbar_limits["CL"],
        limits.xbar_limits["UCL"],
        limits.xbar_limits["LCL"],
        len(subgroups),
    )
    s_vals = subgroups.std(axis=1, ddof=1)
    subgroup_df = pd.DataFrame({
        "subgroup": np.arange(1, len(xbar) + 1),
        "Xbar": xbar,
        "S": s_vals,
    })
    ooc = [
        int(i + 1)
        for i, v in enumerate(xbar)
        if v > limits.xbar_limits["UCL"] or v < limits.xbar_limits["LCL"]
    ]
    norm = NormalityResult("Shapiro-Wilk", 0.98, 0.15 if is_normal else 0.01, is_normal, 0.05, 125)
    cap = _capability_from_indices(cp, cpk)
    return SpcAnalysisResult(
        chart_type="xbar_s",
        normality=norm,
        control_limits=limits,
        capability=cap,
        subgroup_stats=subgroup_df,
        out_of_control_points=ooc,
    )
