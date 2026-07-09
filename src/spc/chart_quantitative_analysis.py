"""관리도 차트 정량 해석 — 이상 시점·산포·분석 기법 명시."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.spc.capability_strategy import CapabilityStrategy, determine_capability_strategy
from src.spc.decision_models import SpcDecisionResult
from src.spc.statistics import SpcAnalysisResult


@dataclass
class ChartQuantInsight:
    chart_name: str
    metric_summary: str
    anomaly_points: list[str]
    dispersion_note: str
    expert_comment: str


@dataclass
class QuantitativeChartAnalysis:
    insights: list[ChartQuantInsight] = field(default_factory=list)
    analysis_technique: str = ""
    technique_rationale: str = ""
    capability_strategy: CapabilityStrategy | None = None
    summary_markdown: str = ""

    def to_markdown(self) -> str:
        return self.summary_markdown


def _fmt_points(indices: list[int], values: list[float] | None = None) -> list[str]:
    out: list[str] = []
    for i, idx in enumerate(indices):
        pt = f"subgroup #{idx + 1}"
        if values and i < len(values):
            pt += f" (값={values[i]:.4f})"
        out.append(pt)
    return out


def analyze_charts_quantitatively(
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> QuantitativeChartAnalysis:
    """차트별 정량 지표·이상 시점·전문가 해석 생성."""
    insights: list[ChartQuantInsight] = []
    cl = analysis.control_limits
    ooc = analysis.out_of_control_points or []
    chart = analysis.chart_type

    is_stable = decision.control_chart.is_stable
    is_normal = decision.normality.is_normal or decision.normality.normality_state == "normal"
    boxcox = bool(decision.normality.applied_action and "Box-Cox" in (decision.normality.applied_action or ""))
    strategy = determine_capability_strategy(is_stable, is_normal, boxcox_success=boxcox)

    # --- 산포 관리도 ---
    if chart in ("xbar_s", "xbar_r") and analysis.subgroup_stats is not None:
        sg = analysis.subgroup_stats
        disp_col = "R" if chart == "xbar_r" and "R" in sg.columns else "S"
        if disp_col in sg.columns:
            disp_vals = sg[disp_col].to_numpy(dtype=float)
            disp_ucl = cl.r_limits.get("UCL") if chart == "xbar_r" else cl.s_limits.get("UCL")
            disp_cl = cl.r_limits.get("CL") if chart == "xbar_r" else cl.s_limits.get("CL")
            disp_ooc_idx = [i for i, v in enumerate(disp_vals) if disp_ucl and v > disp_ucl]
            mean_disp = float(np.mean(disp_vals))
            cv_disp = float(np.std(disp_vals, ddof=1) / mean_disp * 100) if mean_disp else 0
            r_status = decision.control_chart.r_chart_status or "undetermined"
            insights.append(
                ChartQuantInsight(
                    chart_name=f"{disp_col} 관리도 (산포)",
                    metric_summary=(
                        f"평균 {disp_col}={mean_disp:.4f}, CL={disp_cl:.4f}, UCL={disp_ucl:.4f}, "
                        f"산포 변동계수 CV={cv_disp:.1f}%"
                    ),
                    anomaly_points=_fmt_points(disp_ooc_idx, [disp_vals[i] for i in disp_ooc_idx]),
                    dispersion_note=(
                        f"산포 관리도 상태: **{r_status}**. "
                        + (
                            f"UCL 초과 {len(disp_ooc_idx)}점 — 부군 내 변동 급증 시점."
                            if disp_ooc_idx
                            else "UCL 위반 없음 — 단기 산포 안정."
                        )
                    ),
                    expert_comment=(
                        "R/S 차트는 부군 내 산포(재현성)를 모니터링합니다. "
                        "UCL 초과는 측정·공구·원재료 변동 또는 부군 구성 오류를 의심합니다."
                    ),
                )
            )

        if "Xbar" in sg.columns:
            xbar_vals = sg["Xbar"].to_numpy(dtype=float)
            x_ucl = cl.xbar_limits.get("UCL")
            x_lcl = cl.xbar_limits.get("LCL")
            x_cl = cl.xbar_limits.get("CL")
            x_ooc = [i for i in ooc if i < len(xbar_vals)]
            drift = float(xbar_vals[-1] - xbar_vals[0]) if len(xbar_vals) > 1 else 0
            insights.append(
                ChartQuantInsight(
                    chart_name="X-bar 관리도 (위치)",
                    metric_summary=(
                        f"X̿={x_cl:.4f}, 범위=[{float(np.min(xbar_vals)):.4f}, {float(np.max(xbar_vals)):.4f}], "
                        f"전구간 drift={drift:+.4f}"
                    ),
                    anomaly_points=_fmt_points(x_ooc, [xbar_vals[i] for i in x_ooc if i < len(xbar_vals)]),
                    dispersion_note=f"관리한계 UCL={x_ucl:.4f}, LCL={x_lcl:.4f}",
                    expert_comment=(
                        f"평균 관리도 상태: **{decision.control_chart.mean_chart_status or '—'}**. "
                        "연속 상승·하강, 2σ 밴드 밖 다수 점은 공정 평균 이동(setup·온도·마모) 신호입니다."
                    ),
                )
            )

    elif chart == "imr" and analysis.individual_stats is not None:
        ind = analysis.individual_stats
        i_vals = ind["I"].to_numpy(dtype=float) if "I" in ind.columns else np.array([])
        mr_vals = ind["MR"].to_numpy(dtype=float) if "MR" in ind.columns else np.array([])
        i_ucl = cl.i_limits.get("UCL")
        mr_ucl = cl.mr_limits.get("UCL")
        i_ooc = [i for i in ooc if i < len(i_vals)]
        mr_ooc = [i for i, v in enumerate(mr_vals) if mr_ucl and v > mr_ucl]
        if len(i_vals):
            insights.append(
                ChartQuantInsight(
                    chart_name="I 관리도 (개별값)",
                    metric_summary=f"N={len(i_vals)}, 평균={float(np.mean(i_vals)):.4f}, σ_overall={float(np.std(i_vals, ddof=1)):.4f}",
                    anomaly_points=_fmt_points(i_ooc, [i_vals[i] for i in i_ooc if i < len(i_vals)]),
                    dispersion_note=f"UCL={i_ucl:.4f}, LCL={cl.i_limits.get('LCL', 0):.4f}",
                    expert_comment="I 차트는 개별 측정값의 시계열 이상을 감지합니다. LOT·교대 경계와 교차 확인하세요.",
                )
            )
        if len(mr_vals):
            insights.append(
                ChartQuantInsight(
                    chart_name="MR 관리도 (이동범위)",
                    metric_summary=f"평균 MR={float(np.mean(mr_vals)):.4f}, UCL={mr_ucl:.4f}",
                    anomaly_points=_fmt_points(mr_ooc, [mr_vals[i] for i in mr_ooc]),
                    dispersion_note=(
                        f"MR UCL 초과 {len(mr_ooc)}점" if mr_ooc else "MR 안정 — 인접 측정 간 변동 일정"
                    ),
                    expert_comment="MR 차트는 인접 2점 간 변동을 봅니다. MR 불안정 시 I 차트 해석을 보류합니다.",
                )
            )

    # 히스토그램·정규성 정량
    if analysis.capability:
        cap = analysis.capability
        skew_note = ""
        if analysis.normality.n >= 3:
            raw = analysis.metadata.get("raw_values")
            if raw is None and analysis.individual_stats is not None and "I" in analysis.individual_stats.columns:
                raw = analysis.individual_stats["I"].tolist()
            if raw is not None:
                arr = np.asarray(raw, dtype=float)
                arr = arr[~np.isnan(arr)]
                if len(arr) >= 3:
                    from scipy import stats as sp_stats
                    skew = float(sp_stats.skew(arr))
                    kurt = float(sp_stats.kurtosis(arr))
                    skew_note = f"왜도={skew:.2f}, 첨도={kurt:.2f}"
        if cap.usl is not None and cap.lsl is not None:
            spec_note = (
                f"규격폭 대비: (USL−LSL)={cap.usl - cap.lsl:.4f}, "
                f"6σ_within={6 * cap.std_within:.4f}"
            )
        elif cap.usl is not None:
            spec_note = (
                f"편측 상한 USL={cap.usl:g}, USL−Mean={cap.usl - cap.mean:.4f}, "
                f"6σ_within={6 * cap.std_within:.4f}"
            )
        else:
            spec_note = (
                f"편측 하한 LSL={cap.lsl:g}, Mean−LSL={cap.mean - cap.lsl:.4f}, "
                f"6σ_within={6 * cap.std_within:.4f}"
            )
        insights.append(
            ChartQuantInsight(
                chart_name="분포·규격 위치",
                metric_summary=(
                    f"Mean={cap.mean:.4f}, σ_within={cap.std_within:.4f}, σ_overall={cap.std_overall:.4f}"
                    + (f", {skew_note}" if skew_note else "")
                ),
                anomaly_points=[],
                dispersion_note=spec_note,
                expert_comment=decision.normality.handling_recommendation,
            )
        )

    technique = (
        f"{strategy.case_label} → **{strategy.primary_method}** | "
        f"관리도: {analysis.chart_type.upper()} | "
        f"WE Rules 1~5 | 정규성: {decision.normality.test_name}"
    )
    rationale = strategy.method_rationale

    md_lines = [
        "### 적용 분석 기법",
        technique,
        "",
        "**선정 사유:**",
        rationale,
        "",
    ]
    if strategy.follow_up_priorities:
        md_lines.append("**비정규 후속조치 우선순위:**")
        for p in strategy.follow_up_priorities:
            md_lines.append(f"- {p}")
        md_lines.append("")

    for ins in insights:
        md_lines.append(f"#### {ins.chart_name}")
        md_lines.append(f"- **정량 요약:** {ins.metric_summary}")
        if ins.anomaly_points:
            md_lines.append(f"- **이상 시점:** {', '.join(ins.anomaly_points)}")
        md_lines.append(f"- **산포/한계:** {ins.dispersion_note}")
        md_lines.append(f"- **전문가 해석:** {ins.expert_comment}")
        md_lines.append("")

    return QuantitativeChartAnalysis(
        insights=insights,
        analysis_technique=technique,
        technique_rationale=rationale,
        capability_strategy=strategy,
        summary_markdown="\n".join(md_lines),
    )
