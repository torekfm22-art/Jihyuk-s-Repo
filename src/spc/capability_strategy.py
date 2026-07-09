"""정규성·안정성 기반 공정능력 분석 전략 (Case 1~4 + 후속조치 우선순위)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MetricBasis = Literal["CpCpk", "PpPpk"]


@dataclass
class CapabilityStrategy:
    case_id: str
    case_label: str
    is_stable: bool
    is_normal: bool
    primary_method: str
    metric_basis: MetricBasis
    use_non_normal: bool
    follow_up_priorities: list[str]
    method_rationale: str
    transform_recommendation: str | None = None


FOLLOW_UP_PRIORITIES = [
    "1순위: Non-normal capability (percentile/Z-score 기반)",
    "2순위: Box-Cox 변환 (경미한 비정규)",
    "3순위: Johnson 변환 (최후 수단)",
    "4순위: 공정 개선 (근본 원인·분포 자체 문제)",
]


def determine_capability_strategy(
    is_stable: bool,
    is_normal: bool,
    *,
    boxcox_success: bool = False,
    johnson_success: bool = False,
    severe_non_normal: bool = False,
) -> CapabilityStrategy:
    """Case 1~4 분기 및 분석 기법·사유."""
    if is_stable and is_normal:
        return CapabilityStrategy(
            case_id="case1",
            case_label="Case 1: 안정 + 정규",
            is_stable=True,
            is_normal=True,
            primary_method="Cp / Cpk",
            metric_basis="CpCpk",
            use_non_normal=False,
            follow_up_priorities=[],
            method_rationale=(
                "공정이 통계적 관리 상태(In Control)이고 정규성 검정을 통과했으므로 "
                "σ_within 기반 Cp/Cpk가 AIAG 표준 공정능력 지표로 유효합니다."
            ),
        )

    if is_stable and not is_normal:
        transform = None
        if boxcox_success:
            transform = "Box-Cox 변환 적용 후 Cp/Cpk 재평가"
        elif johnson_success:
            transform = "Johnson 변환 적용 후 Cp/Cpk 재평가"
        elif not severe_non_normal:
            transform = "Box-Cox 변환 시도 권고 (경미한 비정규)"
        else:
            transform = "Johnson 변환 또는 공정 개선 검토"

        return CapabilityStrategy(
            case_id="case2",
            case_label="Case 2: 안정 + 비정규",
            is_stable=True,
            is_normal=False,
            primary_method="Non-normal Cp/Cpk",
            metric_basis="CpCpk",
            use_non_normal=True,
            follow_up_priorities=FOLLOW_UP_PRIORITIES.copy(),
            method_rationale=(
                "공정은 안정적이나 정규분포 가정이 성립하지 않습니다. "
                "정규 기반 Cp/Cpk 대신 percentile·경험적 Z-score 기반 Non-normal Cp/Cpk를 "
                "1순위로 적용합니다. 경미한 비정규는 Box-Cox, 지속적 비정규는 Johnson 변환을 "
                "순차 검토하고, 변환 불가 시 공정 개선이 필요합니다."
            ),
            transform_recommendation=transform,
        )

    if not is_stable and is_normal:
        return CapabilityStrategy(
            case_id="case3",
            case_label="Case 3: 불안정 + 정규",
            is_stable=False,
            is_normal=True,
            primary_method="Pp / Ppk",
            metric_basis="PpPpk",
            use_non_normal=False,
            follow_up_priorities=[
                "1순위: 공정 안정화 (특수원인 제거)",
                "2순위: 안정화 후 Cp/Cpk 재평가",
            ],
            method_rationale=(
                "관리도에서 특수원인·이상 패턴이 감지되어 공정이 Out of Control입니다. "
                "σ_within 기반 Cp/Cpk는 유효하지 않으며, 전체 변동(σ_overall)을 반영한 "
                "Pp/Ppk로 현재 성능을 평가합니다. 안정화 후 Cp/Cpk를 재산출해야 합니다."
            ),
        )

    return CapabilityStrategy(
        case_id="case4",
        case_label="Case 4: 불안정 + 비정규",
        is_stable=False,
        is_normal=False,
        primary_method="Non-normal Pp/Ppk (percentile 기반)",
        metric_basis="PpPpk",
        use_non_normal=True,
        follow_up_priorities=FOLLOW_UP_PRIORITIES.copy(),
        method_rationale=(
            "공정 불안정과 비정규가 동시에 존재합니다. Cp/Cpk는 사용할 수 없으며, "
            "percentile·경험적 Z-score 기반 Non-normal Pp/Ppk로 현재 성능을 평가합니다. "
            "안정화와 분포 정상화(또는 Non-normal capability)를 병행 검토해야 합니다."
        ),
        transform_recommendation="안정화 우선 → Non-normal capability → Box-Cox → Johnson → 공정 개선",
    )
