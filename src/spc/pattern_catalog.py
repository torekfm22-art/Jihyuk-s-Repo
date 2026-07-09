"""관리도 이상 패턴 메타정보 카탈로그."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlPatternMeta:
    pattern_id: str
    pattern_name_ko: str
    description: str
    likely_causes: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    severity: str  # low / medium / high / critical


PATTERN_CATALOG: dict[str, ControlPatternMeta] = {
    "control_limit_violation": ControlPatternMeta(
        pattern_id="control_limit_violation",
        pattern_name_ko="관리한계 이탈",
        description="관리한계(UCL/LCL)를 벗어난 점이 존재합니다.",
        likely_causes=(
            "특별원인(설비 이상, 자재 변경, 작업자 실수)",
            "공정 조건 급변",
            "측정 시스템 오류",
        ),
        recommended_actions=(
            "이탈 시점 전후 4M1E 변경 이력 확인",
            "원인 제거 후 재수집",
            "관리한계 재설정 검토",
        ),
        severity="critical",
    ),
    "run_7_same_side": ControlPatternMeta(
        pattern_id="run_7_same_side",
        pattern_name_ko="7연속 동일측",
        description="중심선 기준 동일 방향으로 연속 7점 이상 배치되었습니다.",
        likely_causes=(
            "평균 이동(원료 배치, 셋업 편차)",
            "측정 영점 드리프트",
            "공구 마모",
        ),
        recommended_actions=(
            "평균 위치 원인 분석",
            "공정 중심 재조정",
            "추가 데이터로 추세 확인",
        ),
        severity="high",
    ),
    "trend_7_increasing_or_decreasing": ControlPatternMeta(
        pattern_id="trend_7_increasing_or_decreasing",
        pattern_name_ko="7연속 증감 추세",
        description="연속 7점 이상 단조 증가 또는 감소 추세가 관찰됩니다.",
        likely_causes=(
            "공구 마모",
            "온도·습도 등 환경 변화",
            "원료 특성 변화",
        ),
        recommended_actions=(
            "시간·순번 연계 원인 분석",
            "예방보전·공정 파라미터 재튜닝",
            "추세 지속 여부 모니터링",
        ),
        severity="high",
    ),
    "centerline_bias": ControlPatternMeta(
        pattern_id="centerline_bias",
        pattern_name_ko="중심선 편향",
        description="데이터가 중심선 한쪽에 체계적으로 치우쳐 있습니다.",
        likely_causes=(
            "목표값 대비 셋업 편차",
            "규격 중심과 공정 중심 불일치",
            "측정 바이어스",
        ),
        recommended_actions=(
            "공정 중심 조정",
            "목표값·규격 중심 대비 편차 검토",
            "치우침 방향별 원인 분석",
        ),
        severity="medium",
    ),
    "excessive_scatter": ControlPatternMeta(
        pattern_id="excessive_scatter",
        pattern_name_ko="과도한 산포",
        description="산포 관리도(R/S/MR)에서 변동 증가 신호가 확인됩니다.",
        likely_causes=(
            "고정 불량",
            "공구·치공구 마모",
            "원료 배치 편차",
            "환경 변동",
        ),
        recommended_actions=(
            "산포 원인 우선 제거",
            "R/S/MR 차트 OOC 구간 5W2H 분석",
            "공정 안정화 후 재수집",
        ),
        severity="critical",
    ),
    "periodicity": ControlPatternMeta(
        pattern_id="periodicity",
        pattern_name_ko="주기성 패턴",
        description="데이터에 반복적 주기 패턴이 의심됩니다.",
        likely_causes=(
            "교대·LOT 순환",
            "설비 사이클",
            "원료 공급 주기",
        ),
        recommended_actions=(
            "주기와 연계된 작업조건 교차 분석",
            "교대·LOT별 분리 관리 검토",
            "샘플링 계획 재검토",
        ),
        severity="medium",
    ),
    "near_control_limit": ControlPatternMeta(
        pattern_id="near_control_limit",
        pattern_name_ko="관리한계 근접",
        description="관리한계 1σ 이내에 점이 다수 배치되어 있습니다.",
        likely_causes=(
            "공정 한계 근접 운영",
            "관리한계 대비 변동 증가 전조",
            "셋업 편차 누적",
        ),
        recommended_actions=(
            "관리한계 이탈 전 예방 조치",
            "공정 여유 확보",
            "추가 모니터링 강화",
        ),
        severity="medium",
    ),
    "we_rule_1": ControlPatternMeta(
        pattern_id="we_rule_1",
        pattern_name_ko="WE Rule 1 — 3σ 초과",
        description="1점이 관리한계(3σ)를 벗어났습니다.",
        likely_causes=("특별원인", "공정 조건 급변", "측정 오류"),
        recommended_actions=("이탈 시점 4M1E 확인", "원인 제거 후 재수집"),
        severity="critical",
    ),
    "we_rule_2": ControlPatternMeta(
        pattern_id="we_rule_2",
        pattern_name_ko="WE Rule 2 — 2σ 구간 2/3 연속",
        description="연속 3점 중 2점 이상이 2σ 구간을 벗어났습니다.",
        likely_causes=("평균 이동 전조", "공정 드리프트"),
        recommended_actions=("추세 원인 분석", "공정 중심 재조정"),
        severity="high",
    ),
    "we_rule_3": ControlPatternMeta(
        pattern_id="we_rule_3",
        pattern_name_ko="WE Rule 3 — 1σ 구간 4/5 연속",
        description="연속 5점 중 4점 이상이 1σ 구간을 벗어났습니다.",
        likely_causes=("체계적 편차", "셋업 편차 누적"),
        recommended_actions=("편차 방향 원인 분석", "예방 조치"),
        severity="high",
    ),
    "we_rule_4": ControlPatternMeta(
        pattern_id="we_rule_4",
        pattern_name_ko="WE Rule 4 — 중심선 동일측 연속",
        description="중심선 기준 동일 방향으로 연속 7점 이상 배치되었습니다.",
        likely_causes=("평균 이동", "측정 영점 드리프트", "공구 마모"),
        recommended_actions=("평균 위치 원인 분석", "공정 중심 재조정"),
        severity="high",
    ),
    "we_rule_5": ControlPatternMeta(
        pattern_id="we_rule_5",
        pattern_name_ko="WE Rule 5 — 연속 증감 추세",
        description="연속 7점 이상 단조 증가 또는 감소 추세가 관찰됩니다.",
        likely_causes=("공구 마모", "환경 변화", "원료 특성 변화"),
        recommended_actions=("시간·순번 연계 원인 분석", "예방보전 검토"),
        severity="high",
    ),
}


def get_pattern_meta(pattern_id: str) -> ControlPatternMeta | None:
    return PATTERN_CATALOG.get(pattern_id)
