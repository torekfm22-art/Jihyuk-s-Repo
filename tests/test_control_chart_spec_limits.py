"""관리도 차트 — 규격·관리한계 오른쪽 라벨 (규격선 없음)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.spc.interactive_charts import build_control_chart_figure, build_histogram_figure
from src.spc.statistics import CapabilityResult, ControlLimits, NormalityResult, SpcAnalysisResult


def _sample_analysis() -> SpcAnalysisResult:
    rng = np.random.default_rng(0)
    subgroups = rng.normal(10.0, 0.05, 50).reshape(10, 5)
    xbar = subgroups.mean(axis=1)
    s_vals = subgroups.std(axis=1, ddof=1)
    subgroup_df = pd.DataFrame({
        "subgroup": np.arange(1, 11),
        "Xbar": xbar,
        "S": s_vals,
    })
    limits = ControlLimits(
        chart_type="xbar_s",
        center_line=float(xbar.mean()),
        ucl=float(xbar.mean()) + 0.1,
        lcl=float(xbar.mean()) - 0.1,
        sigma_estimate=0.05,
        subgroup_size=5,
        xbar_limits={"CL": float(xbar.mean()), "UCL": float(xbar.mean()) + 0.1, "LCL": float(xbar.mean()) - 0.1},
        s_limits={"CL": float(s_vals.mean()), "UCL": float(s_vals.mean()) + 0.02, "LCL": 0.0},
    )
    cap = CapabilityResult(
        usl=10.5,
        lsl=9.5,
        mean=float(xbar.mean()),
        std_within=0.05,
        std_overall=0.05,
        cp=1.3,
        cpk=1.2,
        pp=1.3,
        ppk=1.2,
        cpu=1.2,
        cpl=1.2,
        ppm_est=10.0,
    )
    return SpcAnalysisResult(
        chart_type="xbar_s",
        normality=NormalityResult("Shapiro", 0.9, 0.2, True, n=50),
        control_limits=limits,
        capability=cap,
        subgroup_stats=subgroup_df,
    )


def test_control_chart_yaxis_uses_control_limits_not_spec():
    """Y축이 LSL/USL이 아닌 UCL/LCL·데이터 범위로 고정되는지 확인."""
    rng = np.random.default_rng(0)
    subgroups = rng.normal(143.0, 0.05, 50).reshape(10, 5)
    xbar = subgroups.mean(axis=1)
    s_vals = subgroups.std(axis=1, ddof=1)
    subgroup_df = pd.DataFrame({
        "subgroup": np.arange(1, 11),
        "Xbar": xbar,
        "S": s_vals,
    })
    xbar_bar = float(xbar.mean())
    limits = ControlLimits(
        chart_type="xbar_s",
        center_line=xbar_bar,
        ucl=xbar_bar + 0.1,
        lcl=xbar_bar - 0.1,
        sigma_estimate=0.05,
        subgroup_size=5,
        xbar_limits={"CL": xbar_bar, "UCL": xbar_bar + 0.1, "LCL": xbar_bar - 0.1},
        s_limits={"CL": float(s_vals.mean()), "UCL": float(s_vals.mean()) + 0.02, "LCL": 0.0},
    )
    cap = CapabilityResult(
        usl=160.0, lsl=120.0, mean=xbar_bar, std_within=0.05, std_overall=0.05,
        cp=1.3, cpk=1.2, pp=1.3, ppk=1.2, cpu=1.2, cpl=1.2, ppm_est=10.0,
    )
    analysis = SpcAnalysisResult(
        chart_type="xbar_s",
        normality=NormalityResult("Shapiro", 0.9, 0.2, True, n=50),
        control_limits=limits,
        capability=cap,
        subgroup_stats=subgroup_df,
    )
    fig = build_control_chart_figure(analysis, None, set())
    assert fig is not None
    yaxis = fig.layout.yaxis
    assert yaxis.range is not None
    y0, y1 = yaxis.range
    assert y0 > 120.0
    assert y1 < 160.0


def test_histogram_xaxis_uses_control_limits_not_spec():
    raw = np.random.default_rng(1).normal(143.0, 0.05, 80)
    fig = build_histogram_figure(
        raw, float(np.mean(raw)), float(np.std(raw, ddof=1)),
        ucl=143.15, lcl=142.85, cl=143.0, usl=160.0, lsl=120.0,
    )
    x0, x1 = fig.layout.xaxis.range
    assert x0 > 120.0
    assert x1 < 160.0


def test_spec_limits_are_right_labels_not_lines():
    fig = build_control_chart_figure(_sample_analysis(), None, set())
    assert fig is not None

    shapes = fig.layout.shapes or []
    purple_spec_lines = [
        s for s in shapes
        if s.y0 is not None
        and round(float(s.y0), 4) in (9.5, 10.5)
        and getattr(s.line, "color", None) == "#7030A0"
    ]
    assert not purple_spec_lines

    ann_texts = [a.text for a in (fig.layout.annotations or []) if a.text]
    assert any("USL=10.5000" in t for t in ann_texts)
    assert any("LSL=9.5000" in t for t in ann_texts)
    assert any("UCL=" in t for t in ann_texts)
    assert any("CL=" in t for t in ann_texts)
    assert any("LCL=" in t for t in ann_texts)
