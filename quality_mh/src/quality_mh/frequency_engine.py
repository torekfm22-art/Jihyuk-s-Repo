"""발생빈도 자동 계산 엔진."""
from __future__ import annotations

from typing import Optional

from quality_mh.models import FrequencyDB, FrequencyMethod, RuleMaster


def calculate_frequency_weighted_average_excel_style(
    y1: float,
    y2: float,
    y3: float,
    w1: float = 5.0,
    w2: float = 3.0,
    w3: float = 2.0,
) -> tuple[float, dict, list[str]]:
    """3개년 가중평균 발생빈도 산출."""
    log: list[str] = []
    log.append(f"[입력] Y-1 실적={y1}, Y-2 실적={y2}, Y-3 실적={y3}")
    log.append(f"[입력] 가중치 w1={w1}, w2={w2}, w3={w3}")
    weighted_sum = y1 * w1 + y2 * w2 + y3 * w3
    weight_total = w1 + w2 + w3
    log.append(f"[중간] 가중합 = {y1}×{w1} + {y2}×{w2} + {y3}×{w3} = {weighted_sum}")
    log.append(f"[중간] 가중치 합 = {w1}+{w2}+{w3} = {weight_total}")
    frequency = weighted_sum / weight_total
    log.append(f"[공식] 발생빈도 = 가중합 ÷ 가중치합 = {weighted_sum} ÷ {weight_total}")
    log.append(f"[결과] 발생빈도 = {frequency}")
    factors = {
        "y1_actual": y1,
        "y2_actual": y2,
        "y3_actual": y3,
        "weight1": w1,
        "weight2": w2,
        "weight3": w3,
        "weighted_sum": weighted_sum,
        "weight_total": weight_total,
    }
    return frequency, factors, log


def calculate_frequency_plan_linked_excel_style(
    ref_ratio: float,
    plan_qty: float,
) -> tuple[float, dict, list[str]]:
    """생산계획 연동 발생빈도 산출."""
    log: list[str] = []
    log.append(f"[입력] 기준비율(ref_ratio)={ref_ratio}, 당해년 계획생산량(plan_qty)={plan_qty}")
    log.append("[공식] 발생빈도 = 기준비율 × 계획생산량")
    frequency = ref_ratio * plan_qty
    log.append(f"[중간] {ref_ratio} × {plan_qty} = {frequency}")
    log.append(f"[결과] 발생빈도 = {frequency}")
    factors = {"ref_ratio": ref_ratio, "plan_qty": plan_qty}
    return frequency, factors, log


def calculate_frequency_periodic_excel_style(
    cycle_type: str,
    cycle_count: float,
    working_days: float = 20.0,
    working_weeks: float = 4.0,
    working_months: float = 12.0,
) -> tuple[float, dict, list[str]]:
    """수행주기 기반 월 발생빈도 산출."""
    log: list[str] = []
    log.append(
        f"[입력] 수행주기={cycle_type}, 횟수={cycle_count}, "
        f"근무일={working_days}, 근무주={working_weeks}, 근무월={working_months}"
    )
    if cycle_type == "일간":
        log.append(f"[공식] 월 발생빈도 = 횟수 × 근무일수 = {cycle_count} × {working_days}")
        frequency = cycle_count * working_days
    elif cycle_type == "주간":
        log.append(f"[공식] 월 발생빈도 = 횟수 × 근무주수 = {cycle_count} × {working_weeks}")
        frequency = cycle_count * working_weeks
    elif cycle_type == "월간":
        log.append(f"[공식] 월 발생빈도 = 횟수 = {cycle_count}")
        frequency = cycle_count
    elif cycle_type == "분기":
        log.append(f"[공식] 월 발생빈도 = 횟수 × 4 ÷ 12 = {cycle_count} × 4 ÷ 12")
        frequency = cycle_count * 4 / 12
    elif cycle_type == "연간":
        log.append(f"[공식] 월 발생빈도 = 횟수 ÷ 12 = {cycle_count} ÷ 12")
        frequency = cycle_count / 12
    else:
        raise ValueError(f"지원하지 않는 수행주기 유형: {cycle_type}")
    log.append(f"[결과] 월 발생빈도 = {frequency}")
    factors = {
        "cycle_type": cycle_type,
        "cycle_count": cycle_count,
        "working_days": working_days,
        "working_weeks": working_weeks,
        "working_months": working_months,
    }
    return frequency, factors, log


def calculate_frequency_by_task_rule(
    rule: RuleMaster,
    freq_db: FrequencyDB,
    override_value: Optional[float] = None,
) -> tuple[float, FrequencyMethod, dict, list[str], bool]:
    """업무 rule에 따른 발생빈도 메인 디스패처."""
    method = freq_db.frequency_method or rule.frequency_method
    log: list[str] = [f"[시작] 업무={rule.task_name}({rule.task_code}), 산정방식={method.value}"]
    factors: dict = {"task_code": rule.task_code, "task_name": rule.task_name}

    if override_value is not None and override_value > 0:
        log.append(f"[수기입력] 발생빈도 = {override_value} (연간 기준 직접 입력)")
        factors["auto_frequency"] = override_value
        factors["override_value"] = override_value
        log.append(f"[최종] 발생빈도 = {override_value}")
        return override_value, method, factors, log, True

    if method == FrequencyMethod.WEIGHTED_AVG:
        if freq_db.y1_actual is None or freq_db.y2_actual is None or freq_db.y3_actual is None:
            raise ValueError("3개년 가중평균: Y-1/Y-2/Y-3 실적이 모두 필요합니다.")
        auto_freq, factors, sub_log = calculate_frequency_weighted_average_excel_style(
            freq_db.y1_actual,
            freq_db.y2_actual,
            freq_db.y3_actual,
            freq_db.weight1,
            freq_db.weight2,
            freq_db.weight3,
        )
    elif method == FrequencyMethod.PLAN_LINKED:
        if freq_db.ref_ratio is None or freq_db.plan_qty is None:
            raise ValueError("생산계획 연동: ref_ratio와 plan_qty가 필요합니다.")
        auto_freq, factors, sub_log = calculate_frequency_plan_linked_excel_style(
            freq_db.ref_ratio,
            freq_db.plan_qty,
        )
        if freq_db.sampling_type:
            factors["sampling_type"] = freq_db.sampling_type
    elif method == FrequencyMethod.PERIODIC:
        if freq_db.cycle_type is None or freq_db.cycle_count is None:
            raise ValueError("수행주기: cycle_type과 cycle_count가 필요합니다.")
        auto_freq, factors, sub_log = calculate_frequency_periodic_excel_style(
            freq_db.cycle_type,
            freq_db.cycle_count,
            freq_db.working_days,
            freq_db.working_weeks,
            freq_db.working_months,
        )
    else:
        raise ValueError(f"지원하지 않는 발생빈도 산정방식: {method}")

    log.extend(sub_log)
    factors["auto_frequency"] = auto_freq
    factors["task_code"] = rule.task_code
    factors["task_name"] = rule.task_name

    is_overridden = override_value is not None
    final_freq = override_value if is_overridden else auto_freq
    if is_overridden:
        log.append(f"[Override] 자동계산값={auto_freq} → 수기입력값={override_value}")
        factors["override_value"] = override_value
        if auto_freq != 0:
            factors["override_diff_rate"] = (override_value - auto_freq) / auto_freq
    log.append(f"[최종] 발생빈도 = {final_freq}")

    return final_freq, method, factors, log, is_overridden
