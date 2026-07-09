"""공정 상태 자동 진단 (AIAG & VDA SPC Yellow Volume / IATF 16949 기준).

기존 통계·판정 계산 함수는 수정하지 않고, 판정 결과를 해석하는 독립 모듈입니다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from src.spc.decision_models import SpcDecisionResult

# ── 진단 기준값 (고객사별 변경 가능하도록 상수로 분리) ──────────────
DIAG_THRESHOLD_IDEAL = 1.67  # 신규 공정 / 기계 성능 / PPAP 기준
DIAG_THRESHOLD_PASS = 1.33  # 양산 공정 기준 (IATF 16949)
DIAG_THRESHOLD_MINIMUM = 1.00  # 최소 합격선
DIAG_RATIO_STABLE = 0.90  # Cpk/Ppk 안정 판정 하한
DIAG_RATIO_CAUTION = 0.75  # Cpk/Ppk 주의 판정 하한
DIAG_SAMPLE_MIN = 125  # AIAG 권장 최소 데이터 수

# 공정 단계 상수
STAGE_MACHINE = "machine"  # 기계 성능 검증 (Pm/Pmk)
STAGE_PRELIMINARY = "preliminary"  # 초기 공정 검증 (Pp/Ppk, PPAP)
STAGE_PRODUCTION = "production"  # 양산 중 관리 (Cp/Cpk + Pp/Ppk)

Severity = Literal["ok", "warn", "bad", "neutral"]

STAGE_LABEL_KO = {
    STAGE_MACHINE: "기계 성능 검증",
    STAGE_PRELIMINARY: "초기 공정 검증 (PPAP)",
    STAGE_PRODUCTION: "양산 공정 관리",
}

OVERALL_VERDICT_KO = {
    "ok": "양호 — 공정 안정·능력 충족",
    "warn": "주의 — 개선·모니터링 필요",
    "bad": "부적합 — 즉시 조치 필요",
    "neutral": "판정 불가 — 데이터 확인 필요",
}


def _nan_none(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def map_pipeline_stage_to_diag_stage(
    pipeline_stage: str,
    *,
    machine_stages: tuple[str, ...] = (),
) -> str:
    """파이프라인 stage 코드 → 진단 단계 상수."""
    if pipeline_stage in machine_stages:
        return STAGE_MACHINE
    if pipeline_stage == "mass_production":
        return STAGE_PRODUCTION
    return STAGE_PRELIMINARY


def get_pass_threshold(diag_stage: str) -> float:
    """단계별 합격 기준 KPI 하한."""
    if diag_stage == STAGE_PRODUCTION:
        return DIAG_THRESHOLD_PASS
    return DIAG_THRESHOLD_IDEAL


def select_diagnosis_kpi(
    diag_stage: str,
    *,
    cp_cpk_valid: bool,
    cpk: float | None,
    ppk: float | None,
) -> tuple[str, float | None]:
    """진단에 사용할 주 KPI 이름과 값."""
    cpk_v = _nan_none(cpk)
    ppk_v = _nan_none(ppk)
    if diag_stage == STAGE_PRODUCTION and cp_cpk_valid and cpk_v is not None:
        return "Cpk", cpk_v
    if ppk_v is not None:
        return "Ppk", ppk_v
    if cpk_v is not None:
        return "Cpk", cpk_v
    return "Ppk", ppk_v


def classify_capability_index(
    value: float | None,
    diag_stage: str,
) -> tuple[str, Severity]:
    """능력지수 수준 분류 → (한글 라벨, 심각도)."""
    v = _nan_none(value)
    if v is None:
        return "산출 불가", "neutral"

    pass_th = get_pass_threshold(diag_stage)
    if v >= DIAG_THRESHOLD_IDEAL:
        return f"이상 (≥{DIAG_THRESHOLD_IDEAL:.2f})", "ok"
    if v >= pass_th:
        return f"합격 (≥{pass_th:.2f})", "ok"
    if v >= DIAG_THRESHOLD_MINIMUM:
        return f"최소 (≥{DIAG_THRESHOLD_MINIMUM:.2f})", "warn"
    return f"부적합 (<{DIAG_THRESHOLD_MINIMUM:.2f})", "bad"


def evaluate_cpk_ppk_ratio(
    cpk: float | None,
    ppk: float | None,
) -> tuple[float | None, str, Severity]:
    """단기·장기 능력 비율 (Cpk/Ppk) 평가."""
    cpk_v = _nan_none(cpk)
    ppk_v = _nan_none(ppk)
    if cpk_v is None or ppk_v is None or ppk_v <= 0:
        return None, "비교 불가 (Cpk 또는 Ppk 없음)", "neutral"

    ratio = cpk_v / ppk_v
    if ratio >= DIAG_RATIO_STABLE:
        return ratio, f"안정 (비율 {ratio:.2f} ≥ {DIAG_RATIO_STABLE:.2f})", "ok"
    if ratio >= DIAG_RATIO_CAUTION:
        return ratio, f"주의 (비율 {ratio:.2f}, 산포·중심 이동 점검)", "warn"
    return ratio, f"불안정 (비율 {ratio:.2f} < {DIAG_RATIO_CAUTION:.2f})", "bad"


def evaluate_sample_adequacy(n: int) -> tuple[str, Severity]:
    """표본 수 적정성 (AIAG 권장 N≥125)."""
    if n <= 0:
        return "표본 수 미확인", "neutral"
    if n >= DIAG_SAMPLE_MIN:
        return f"적정 (N={n} ≥ {DIAG_SAMPLE_MIN})", "ok"
    return f"부족 (N={n} < {DIAG_SAMPLE_MIN}, 추가 수집 권장)", "warn"


def evaluate_normality_for_diagnosis(
    is_normal: bool,
    *,
    transform_success: bool = False,
) -> tuple[str, Severity]:
    if is_normal:
        return "정규 (Normal)", "ok"
    if transform_success:
        return "변환 후 정규 (Transformed)", "warn"
    return "비정규 (Non-normal)", "bad"


def evaluate_control_stability(
    is_stable: bool,
    *,
    has_we_violations: bool,
    process_change_detected: bool,
) -> tuple[str, Severity]:
    if process_change_detected:
        return "공정 변경 감지 — 관리한계 재설정 필요", "bad"
    if is_stable and not has_we_violations:
        return "안정 (In Control)", "ok"
    if is_stable and has_we_violations:
        return "통계적 안정이나 WE Rule 위반", "warn"
    return "불안정 (Out of Control)", "bad"


def _worst_severity(*levels: Severity) -> Severity:
    order = {"bad": 3, "warn": 2, "ok": 1, "neutral": 0}
    return max(levels, key=lambda s: order.get(s, 0))


@dataclass
class DiagnosisCheckItem:
    category: str
    verdict: str
    severity: Severity
    detail: str = ""

    def to_line(self) -> str:
        if self.detail:
            return f"  · {self.category}: {self.verdict} — {self.detail}"
        return f"  · {self.category}: {self.verdict}"


@dataclass
class ProcessStateDiagnosis:
    diag_stage: str
    diag_stage_label: str
    overall_verdict: str
    overall_severity: Severity
    primary_kpi: str
    primary_kpi_value: float | None
    capability_level: str
    capability_severity: Severity
    cpk_ppk_ratio: float | None
    ratio_verdict: str
    ratio_severity: Severity
    sample_verdict: str
    sample_severity: Severity
    normality_verdict: str
    normality_severity: Severity
    control_verdict: str
    control_severity: Severity
    pass_threshold: float
    checklist: list[DiagnosisCheckItem] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def format_detail_text(self) -> str:
        lines = [
            f"진단 단계: {self.diag_stage_label}",
            f"주 KPI: {self.primary_kpi}"
            + (f" = {self.primary_kpi_value:.3f}" if self.primary_kpi_value is not None else " —"),
            f"합격 기준: ≥ {self.pass_threshold:.2f}",
            "",
            "[항목별 진단]",
        ]
        lines.extend(item.to_line() for item in self.checklist)
        if self.recommendations:
            lines.append("")
            lines.append("[권고 조치]")
            lines.extend(f"  → {r}" for r in self.recommendations)
        return "\n".join(lines)


def diagnose_process_state(
    *,
    cp: float | None,
    cpk: float | None,
    pp: float | None,
    ppk: float | None,
    n: int,
    subgroup_size: int | None,
    is_normal: bool,
    is_stable: bool,
    cp_cpk_valid: bool,
    pipeline_stage: str,
    machine_stages: tuple[str, ...] = (),
    has_we_violations: bool = False,
    process_change_detected: bool = False,
    transform_success: bool = False,
) -> ProcessStateDiagnosis:
    """공정 상태 종합 자동 진단."""
    diag_stage = map_pipeline_stage_to_diag_stage(
        pipeline_stage, machine_stages=machine_stages
    )
    pass_th = get_pass_threshold(diag_stage)
    kpi_name, kpi_val = select_diagnosis_kpi(
        diag_stage, cp_cpk_valid=cp_cpk_valid, cpk=cpk, ppk=ppk
    )
    cap_level, cap_sev = classify_capability_index(kpi_val, diag_stage)
    ratio, ratio_verdict, ratio_sev = evaluate_cpk_ppk_ratio(cpk, ppk)
    sample_verdict, sample_sev = evaluate_sample_adequacy(n)
    norm_verdict, norm_sev = evaluate_normality_for_diagnosis(
        is_normal, transform_success=transform_success
    )
    ctrl_verdict, ctrl_sev = evaluate_control_stability(
        is_stable,
        has_we_violations=has_we_violations,
        process_change_detected=process_change_detected,
    )

    checklist = [
        DiagnosisCheckItem("공정 안정성", ctrl_verdict, ctrl_sev),
        DiagnosisCheckItem("정규성", norm_verdict, norm_sev),
        DiagnosisCheckItem(
            f"능력 ({kpi_name})",
            cap_level,
            cap_sev,
            detail=f"값={kpi_val:.3f}" if kpi_val is not None else "",
        ),
        DiagnosisCheckItem("Cpk/Ppk 비율", ratio_verdict, ratio_sev),
        DiagnosisCheckItem("표본 수", sample_verdict, sample_sev),
    ]

    if diag_stage == STAGE_PRODUCTION and cp_cpk_valid:
        ppk_v = _nan_none(ppk)
        pp_v = _nan_none(pp)
        if ppk_v is not None:
            ppk_level, ppk_sev = classify_capability_index(ppk_v, STAGE_PRELIMINARY)
            checklist.append(
                DiagnosisCheckItem(
                    "장기 능력 (Ppk)",
                    ppk_level,
                    ppk_sev,
                    detail=f"Pp={pp_v:.3f}" if pp_v is not None else "",
                )
            )

    recommendations: list[str] = []
    if ctrl_sev == "bad":
        recommendations.append("특별원인 제거 후 관리도 재평가 및 관리한계 재계산")
    if norm_sev == "bad":
        recommendations.append("비정규 분포 대응(변환·백분위수 기반) 후 능력 재평가")
    elif norm_sev == "warn":
        recommendations.append("변환 적용 데이터로 능력·관리도 해석 유지, 원시 데이터 병행 모니터링")
    if cap_sev == "bad":
        recommendations.append("공정 개선(변동·중심) 후 재능력 평가 및 PPAP/고객 승인")
    elif cap_sev == "warn":
        recommendations.append("능력지수 추세 모니터링 및 예방 조치 검토")
    if ratio_sev in ("warn", "bad"):
        recommendations.append("단기·장기 산포 차이 원인 분석(설비·재료·방법)")
    if sample_sev == "warn":
        recommendations.append(f"AIAG 권장 최소 N={DIAG_SAMPLE_MIN} 이상 추가 데이터 수집")
    if process_change_detected:
        recommendations.append("공정 변경 체크리스트 완료 후 데이터 재수집")
    if not recommendations and cap_sev == "ok" and ctrl_sev == "ok":
        recommendations.append("현 수준 유지·정기 SPC 모니터링")

    overall_sev = _worst_severity(
        cap_sev, ctrl_sev, norm_sev, ratio_sev, sample_sev
    )
    if kpi_val is None:
        overall_sev = "neutral"

    return ProcessStateDiagnosis(
        diag_stage=diag_stage,
        diag_stage_label=STAGE_LABEL_KO.get(diag_stage, diag_stage),
        overall_verdict=OVERALL_VERDICT_KO.get(overall_sev, overall_sev),
        overall_severity=overall_sev,
        primary_kpi=kpi_name,
        primary_kpi_value=kpi_val,
        capability_level=cap_level,
        capability_severity=cap_sev,
        cpk_ppk_ratio=ratio,
        ratio_verdict=ratio_verdict,
        ratio_severity=ratio_sev,
        sample_verdict=sample_verdict,
        sample_severity=sample_sev,
        normality_verdict=norm_verdict,
        normality_severity=norm_sev,
        control_verdict=ctrl_verdict,
        control_severity=ctrl_sev,
        pass_threshold=pass_th,
        checklist=checklist,
        recommendations=recommendations,
    )


def diagnose_from_spc_decision(
    decision: SpcDecisionResult,
    *,
    sample_count: int | None = None,
    machine_stages: tuple[str, ...] | None = None,
) -> ProcessStateDiagnosis:
    """SpcDecisionResult → 공정 상태 진단 (GUI·보고서 연동용)."""
    if machine_stages is None:
        from src.spc.policy_config import SpcPolicyConfig

        machine_stages = tuple(SpcPolicyConfig.from_yaml().machine_capability_recommended_stages)

    cap = decision.capability
    meta = decision.metadata
    n = sample_count if sample_count and sample_count > 0 else 0

    return diagnose_process_state(
        cp=cap.cp if cap else None,
        cpk=cap.cpk if cap else None,
        pp=cap.pp if cap else None,
        ppk=cap.ppk if cap else None,
        n=n,
        subgroup_size=meta.subgroup_size,
        is_normal=decision.normality.is_normal,
        is_stable=decision.control_chart.is_stable,
        cp_cpk_valid=cap.cp_cpk_valid if cap else False,
        pipeline_stage=meta.stage,
        machine_stages=machine_stages,
        has_we_violations=bool(decision.control_chart.western_electric_violations),
        process_change_detected=meta.process_change_detected,
        transform_success=decision.normality.transform_success,
    )
