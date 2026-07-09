"""해석용 관리도 — 공정 안정성 중심 상세 해석 (AIAG-VDA / Western Electric)."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.spc.chart_quantitative_analysis import QuantitativeChartAnalysis, analyze_charts_quantitatively
from src.spc.decision_models import DetectedPattern, SpcDecisionResult
from src.spc.statistics import SpcAnalysisResult


@dataclass
class ImprovementAction:
    priority: int
    category: str
    action: str
    rationale: str

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "category": self.category,
            "action": self.action,
            "rationale": self.rationale,
        }


@dataclass
class ControlChartInterpretation:
    """해석용 관리도 종합 해석 결과."""

    headline: str
    stability_verdict: str
    stability_detail: str
    dispersion_status: str
    mean_status: str
    we_summary: str
    pattern_narratives: list[str]
    operator_checklist: list[str]
    improvement_actions: list[ImprovementAction]
    cp_cpk_gate_message: str
    primary_kpi_guidance: str
    quantitative: QuantitativeChartAnalysis | None = None
    analysis_technique: str = ""
    technique_rationale: str = ""

    def to_markdown(self) -> str:
        lines = [
            f"## {self.headline}",
            "",
            f"**판정:** {self.stability_verdict}",
            "",
            self.stability_detail,
            "",
            "### 차트별 상태",
            f"- **산포 관리도 (R/S/MR):** {self.dispersion_status}",
            f"- **평균 관리도 (Xbar/I):** {self.mean_status}",
            "",
            "### Western Electric Rules",
            self.we_summary,
            "",
        ]
        if self.pattern_narratives:
            lines.append("### 감지된 이상 패턴 해석")
            for n in self.pattern_narratives:
                lines.append(f"- {n}")
            lines.append("")
        if self.operator_checklist:
            lines.append("### 현장 점검 체크리스트")
            for c in self.operator_checklist:
                lines.append(f"- [ ] {c}")
            lines.append("")
        if self.improvement_actions:
            lines.append("### 공정 개선 포인트 (우선순위)")
            for a in sorted(self.improvement_actions, key=lambda x: x.priority):
                lines.append(f"{a.priority}. **[{a.category}]** {a.action}")
                lines.append(f"   - *근거:* {a.rationale}")
            lines.append("")
        lines.extend([
            "### 후속 평가 안내",
            self.cp_cpk_gate_message,
            "",
            self.primary_kpi_guidance,
        ])
        if self.analysis_technique:
            lines.extend(["", "### 적용 분석 기법", self.analysis_technique, "", self.technique_rationale])
        if self.quantitative and self.quantitative.summary_markdown:
            lines.extend(["", self.quantitative.summary_markdown])
        return "\n".join(lines)


def _dispersion_label(chart_type: str) -> str:
    return {"xbar_r": "R", "xbar_s": "S", "imr": "MR"}.get(chart_type, "산포")


def _pattern_narrative(p: DetectedPattern) -> str:
    pts = ", ".join(str(x) for x in p.affected_points[:8])
    suffix = f" … 외 {len(p.affected_points) - 8}건" if len(p.affected_points) > 8 else ""
    causes = " / ".join(p.likely_causes[:2])
    actions = " → ".join(p.recommended_actions[:2])
    return (
        f"**{p.pattern_name_ko}** (심각도: {p.severity}) — subgroup/point {pts}{suffix}. "
        f"가능 원인: {causes}. 권고: {actions}."
    )


def _build_improvement_actions(
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> list[ImprovementAction]:
    actions: list[ImprovementAction] = []
    ctrl = decision.control_chart
    cap = decision.capability
    comp = decision.compliance

    if not ctrl.is_stable:
        if ctrl.r_chart_status == "unstable":
            actions.append(ImprovementAction(
                1, "산포(변동)",
                "R/S/MR 관리도 OOC 구간의 4M1E(설비·치공구·원료·작업자·환경) 변경 이력 확인",
                "산포 관리도 불안정 시 평균 조정보다 변동 원인 제거가 선행되어야 Cp/Cpk 해석이 유효합니다.",
            ))
            actions.append(ImprovementAction(
                2, "산포(변동)",
                "고정 불량·공구 마모·원료 배치 편차·환경 변동 여부를 OOC subgroup 기준으로 5W2H 분석",
                "AIAG-VDA: R-chart-first — 산포 안정화 전 평균 관리도 해석을 보류합니다.",
            ))
        for v in ctrl.western_electric_violations:
            if v.rule_id.startswith("CO_"):
                actions.append(ImprovementAction(
                    3, "평균(위치)",
                    f"{v.rule_name} — subgroup({', '.join(str(p) for p in v.affected_subgroups[:5])}) 확인",
                    "회사 표준 관리도 해석 (첨부#2)",
                ))
            elif v.rule_id in ("WE_R1", "WE_R2", "WE_R3"):
                actions.append(ImprovementAction(
                    3, "평균(위치)",
                    f"{v.rule_id} 위반 subgroup({', '.join(str(p) for p in v.affected_subgroups[:5])}) 전후 셋업·원료·측정 조건 교차 확인",
                    v.rule_name,
                ))
            elif v.rule_id == "WE_R4":
                actions.append(ImprovementAction(
                    4, "평균(위치)",
                    "연속 동일측 배치 — 공정 중심·목표값·영점 드리프트 점검 및 중심 재조정(centering)",
                    "Rule 4: 체계적 평균 이동 신호",
                ))
            elif v.rule_id == "WE_R5":
                actions.append(ImprovementAction(
                    5, "추세",
                    "단조 증감 추세 — 공구 마모·온도·원료 특성 변화 등 시간 연계 원인 분석·예방보전",
                    "Rule 5: 추세(Trend) — 특별원인 또는 점진적 공정 변화",
                ))

        actions.append(ImprovementAction(
            6, "재수집",
            "원인 제거 후 20~25 subgroup 재수집 → 관리한계 재계산 → 해석용 관리도 재평가",
            "불안정 상태에서는 현 관리한계 기반 현장 운영 관리도 적용이 부적절합니다.",
        ))

    if cap and cap.improvement_focus == "centering" and ctrl.is_stable and cap.cpk is not None:
        actions.append(ImprovementAction(
            10, "능력(중심)",
            "공정 폭(산포)은 충분 — 셋업값·목표값 조정으로 규격 중심 대비 평균 위치 개선",
            f"Cpk={cap.cpk:.3f} 미달, Cp={cap.cp:.3f} 양호" if cap.cp is not None else f"Cpk={cap.cpk:.3f} 미달",
        ))
    elif cap and cap.improvement_focus == "variation" and ctrl.is_stable and cap.cpk is not None and cap.cp is not None:
        actions.append(ImprovementAction(
            10, "능력(산포)",
            "설비·치공구·자재·측정 요인 점검으로 공정 변동(σ) 축소",
            f"Cp·Cpk 모두 기준 미달 (Cp={cap.cp:.3f}, Cpk={cap.cpk:.3f})",
        ))

    if comp.requires_recollection:
        actions.append(ImprovementAction(
            15, "데이터",
            "subgroup rationality·정규성·표본 수 기준 미달 — 채취 계획 재검토 후 데이터 재수집",
            "판정 신뢰도 확보를 위해 sampling plan review 필요",
        ))

    if not actions and ctrl.is_stable:
        actions.append(ImprovementAction(
            20, "유지",
            "현 관리한계 유지 + 정기 모니터링(주/월) + 공정 변경 시 관리한계 재설정",
            "Stable (In Control) — 특별원인 신호 없음",
        ))

    return actions


def build_control_chart_interpretation(
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> ControlChartInterpretation:
    """해석용 관리도 기반 공정 안정성 상세 해석."""
    ctrl = decision.control_chart
    cap = decision.capability
    meta = decision.metadata
    disp_name = _dispersion_label(analysis.chart_type)

    if ctrl.is_stable:
        headline = "공정 안정성 점검 — Stable (In Control)"
        stability_verdict = "Stable (In Control) — 통계적 관리 상태"
        stability_detail = (
            "해석용 관리도 기준으로 **특별원인(Special Cause) 신호가 확인되지 않았습니다**. "
            "Western Electric Rules 위반이 없고, 산포·평균 관리도 모두 관리한계 내에서 운영된 것으로 판단됩니다. "
            "이 상태에서 Cp/Cpk 기반 **공정능력(Capability)** 평가가 유효합니다."
        )
    else:
        headline = "공정 안정성 점검 — Unstable (Out of Control)"
        stability_verdict = "Unstable (Out of Control) — 통계적 관리 상태 아님"
        stability_detail = (
            "해석용 관리도에서 **이상 패턴 또는 관리한계 이탈**이 확인되었습니다. "
            "공정이 통계적으로 안정 상태가 아니므로 **Cp/Cpk는 Invalid**(참고용)이며, "
            "**Ppk 중심 공정 성능(Performance)** 평가를 우선해야 합니다. "
            "원인 제거 및 재수집 전까지 현장 운영용 관리도 적용을 제한합니다."
        )

    r_st = ctrl.r_chart_status
    m_st = ctrl.mean_chart_status
    if r_st == "unstable":
        dispersion_status = f"불안정 — {disp_name} 차트 UCL 초과 (산포 증가)"
    elif r_st == "stable":
        dispersion_status = f"안정 — {disp_name} 차트 관리한계 내"
    else:
        dispersion_status = f"해당 없음 또는 미평가 ({disp_name})"

    if m_st == "deferred":
        mean_status = "보류 — 산포 불안정으로 평균 관리도 해석 연기 (R-chart-first)"
    elif m_st == "unstable" or not ctrl.is_stable:
        mean_status = "불안정 — Xbar/I 차트 이상 패턴 또는 OOC"
    elif m_st == "stable":
        mean_status = "안정 — Xbar/I 차트 관리한계 내"
    else:
        mean_status = "평가 완료"

    if ctrl.western_electric_violations:
        we_lines = [
            f"**{v.rule_name}**: {v.occurrence_count}회 "
            f"(subgroup {', '.join(str(p) for p in v.affected_subgroups[:10])})"
            for v in ctrl.western_electric_violations
        ]
        we_summary = "회사 표준 이상 패턴:\n" + "\n".join(f"- {line}" for line in we_lines)
    else:
        we_summary = "회사 표준: 이상 신호 없음 — 관리상태"

    pattern_narratives = [_pattern_narrative(p) for p in ctrl.detected_patterns if p.severity in ("critical", "high")]
    for p in ctrl.detected_patterns:
        if p.severity == "medium" and p.pattern_id not in {x.pattern_id for x in ctrl.detected_patterns if x.severity in ("critical", "high")}:
            pattern_narratives.append(_pattern_narrative(p))

    checklist = [
        "OOC·WE Rules 위반 subgroup의 LOT·교대·작업자·설비 이력 확인",
        "4M1E(Man/Machine/Material/Method/Environment) 변경점 기록",
        "측정 시스템(MSA) — 영점·게이지·반복성 이상 여부",
        "R/S/MR OOC 시: 고정·공구·원료 배치 / Xbar OOC 시: 셋업·목표값·원료 특성",
        "조치 후 20~25 subgroup 재수집 및 관리한계 재계산",
    ]
    if meta.process_change_detected:
        checklist.insert(0, "공정 변경 전 데이터 제외 — 변경 후 데이터만으로 관리한계 재설정")

    if ctrl.is_stable and cap and cap.cp_cpk_valid:
        cp_cpk_gate = (
            "✅ **Cp/Cpk Valid** — 공정 안정 + 정규성·subgroup 조건 충족. "
            "잠재 공정능력(Capability) 해석을 수행할 수 있습니다."
        )
    elif not ctrl.is_stable:
        cp_cpk_gate = (
            "⛔ **Cp/Cpk 미산출** — 비관리상태. Cp/Cpk 계산을 수행하지 않으며, "
            "**Ppk**로 현재 공정 성능을 판단하십시오."
        )
    else:
        cp_cpk_gate = (
            "⚠️ **Cp/Cpk 조건부 Invalid** — 안정성 외 정규성·subgroup 등 추가 조건 미충족. "
            f"사유: {cap.cp_cpk_validity_note if cap else '미평가'}"
        )

    if cap:
        cpk_ref = f"{cap.cpk:.3f}" if cap.cpk is not None else "미산출"
        cp_ref = f"{cap.cp:.3f}" if cap.cp is not None else "미산출"
        if cap.primary_kpi == "Ppk":
            kpi_guidance = (
                f"**Primary KPI: Ppk = {cap.ppk:.3f}** (Performance). "
                f"Cp/Cpk: {cpk_ref} (비관리상태 시 미산출). Gap 해석: {cap.gap_interpretation}"
            )
        else:
            kpi_guidance = (
                f"**Primary KPI: Cpk = {cpk_ref}** (Capability). "
                f"Ppk={cap.ppk:.3f}. 공정 레벨: {cap.process_level}"
            )
    else:
        kpi_guidance = "USL/LSL 미지정 — 공정능력 지표 미산출"

    quant = analyze_charts_quantitatively(analysis, decision)

    return ControlChartInterpretation(
        headline=headline,
        stability_verdict=stability_verdict,
        stability_detail=stability_detail,
        dispersion_status=dispersion_status,
        mean_status=mean_status,
        we_summary=we_summary,
        pattern_narratives=pattern_narratives,
        operator_checklist=checklist,
        improvement_actions=_build_improvement_actions(analysis, decision),
        cp_cpk_gate_message=cp_cpk_gate,
        primary_kpi_guidance=kpi_guidance,
        quantitative=quant,
        analysis_technique=quant.analysis_technique,
        technique_rationale=quant.technique_rationale,
    )
