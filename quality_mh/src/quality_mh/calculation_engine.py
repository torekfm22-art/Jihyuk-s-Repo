"""표준공수 ~ 집계 계산 엔진."""
from __future__ import annotations

import math
from typing import Literal

from quality_mh.frequency_engine import calculate_frequency_by_task_rule
from quality_mh.models import (
    CalcResult,
    FrequencyDB,
    JudgmentStatus,
    QuantitativeRecord,
    RoundingPolicy,
    RuleMaster,
)


def calculate_standard_work_time_excel_style(
    unit_time_min: float,
    frequency: float,
) -> tuple[float, float, list[str]]:
    """표준 작업시간(hr) 산출."""
    log: list[str] = []
    log.append(f"[입력] 단위시간={unit_time_min}분, 발생빈도={frequency}")
    unit_time_hr = unit_time_min / 60
    log.append(f"[중간] 단위시간(hr) = {unit_time_min} ÷ 60 = {unit_time_hr}")
    standard_work_time = unit_time_hr * frequency
    log.append(f"[공식] 표준작업시간 = 단위시간(hr) × 발생빈도 = {unit_time_hr} × {frequency}")
    log.append(f"[결과] 표준작업시간 = {standard_work_time} hr")
    return standard_work_time, unit_time_hr, log


def apply_allowance(
    work_time_hr: float,
    allowance_rate: float = 0.10,
) -> tuple[float, list[str]]:
    """부가공수 반영."""
    log: list[str] = []
    log.append(f"[입력] 표준작업시간={work_time_hr} hr, 부가공수율={allowance_rate}")
    multiplier = 1 + allowance_rate
    final = work_time_hr * multiplier
    log.append(f"[공식] 최종작업시간 = 표준작업시간 × (1 + 부가공수율) = {work_time_hr} × {multiplier}")
    log.append(f"[결과] 최종작업시간 = {final} hr")
    return final, log


def calculate_standard_mh_excel_style(
    final_work_time_hr: float,
    work_hours_per_month: float = 200.0,
    work_hours_per_year: float = 2400.0,
    calc_unit: Literal["월", "연"] = "월",
) -> tuple[float, float, list[str]]:
    """표준공수(M/H, M/D) 산출."""
    log: list[str] = []
    log.append(f"[입력] 최종작업시간={final_work_time_hr} hr, 기준단위={calc_unit}")
    if calc_unit == "월":
        base_hours = work_hours_per_month
        log.append(f"[기준] 1인 월 근무시간 = {work_hours_per_month} hr")
    else:
        base_hours = work_hours_per_year
        log.append(f"[기준] 1인 연 근무시간 = {work_hours_per_year} hr")
    standard_mh = final_work_time_hr / base_hours
    standard_md = standard_mh / 10
    log.append(f"[공식] 표준공수(M/H) = 최종작업시간 ÷ 기준근무시간 = {final_work_time_hr} ÷ {base_hours}")
    log.append(f"[공식] 표준공수(M/D) = M/H ÷ 10 = {standard_mh} ÷ 10")
    log.append(f"[결과] M/H={standard_mh}, M/D={standard_md}")
    return standard_mh, standard_md, log


def round_headcount_standard_rule(mh: float) -> tuple[int, list[str]]:
    """표준공수 올림법 정수화."""
    log: list[str] = []
    log.append(f"[입력] 표준공수(M/H)={mh}")
    n = math.floor(mh)
    threshold = n * 1.1
    log.append(f"[중간] n=floor({mh})={n}, 기준값 n×1.1={threshold}")
    if mh >= threshold:
        headcount = n + 1
        log.append(f"[판정] {mh} >= {threshold} → {n}+1 = {headcount}명")
    else:
        headcount = max(n, 1)
        log.append(f"[판정] {mh} < {threshold} → max({n}, 1) = {headcount}명")
    log.append(f"[결과] 표준인원 = {headcount}명")
    return headcount, log


def round_headcount_even_shift_rule(mh: float) -> tuple[int, list[str]]:
    """주야교대 짝수 정수화."""
    base, base_log = round_headcount_standard_rule(mh)
    log = base_log.copy()
    if base % 2 == 0:
        headcount = base
        log.append(f"[주야교대] {base}는 짝수 → {headcount}명")
    else:
        headcount = base + 1
        log.append(f"[주야교대] {base}는 홀수 → 짝수로 올림 {headcount}명")
    log.append(f"[결과] 표준인원(주야교대) = {headcount}명")
    return headcount, log


def round_headcount(mh: float, policy: RoundingPolicy) -> tuple[int, float, list[str]]:
    """정책별 표준인원 정수화."""
    log: list[str] = [f"[입력] 정수화 정책={policy.value}, M/H={mh}"]
    if policy == RoundingPolicy.CEIL:
        headcount = max(math.ceil(mh), 1)
        log.append(f"[공식] 일반올림 ceil({mh}) = {headcount}명")
    elif policy == RoundingPolicy.STANDARD:
        headcount, sub_log = round_headcount_standard_rule(mh)
        log.extend(sub_log)
    elif policy == RoundingPolicy.EVEN_SHIFT:
        headcount, sub_log = round_headcount_even_shift_rule(mh)
        log.extend(sub_log)
    elif policy == RoundingPolicy.MANUAL:
        headcount = max(math.ceil(mh), 1)
        log.append(f"[수동조정] 기본 ceil({mh})={headcount} (UI에서 수동 변경 가능)")
    else:
        headcount, sub_log = round_headcount_standard_rule(mh)
        log.extend(sub_log)
    return headcount, mh, log


def _meta(result: CalcResult, key: str, default: str = "미지정") -> str:
    val = result.frequency_factors_used.get(key)
    return str(val) if val is not None else default


def _active_results(records: list[CalcResult]) -> list[CalcResult]:
    return [
        r for r in records
        if r.frequency_factors_used.get("judgment_status", JudgmentStatus.CONFIRMED.value)
        != JudgmentStatus.EXCLUDED.value
    ]


def aggregate_by_line(records: list[CalcResult]) -> dict:
    """라인별 집계."""
    groups: dict[str, dict] = {}
    for r in _active_results(records):
        key = _meta(r, "line")
        if key not in groups:
            groups[key] = {
                "line": key,
                "plant": _meta(r, "plant"),
                "wg": _meta(r, "wg"),
                "standard_mh": 0.0,
                "standard_headcount": 0,
                "final_work_time_hr": 0.0,
                "record_count": 0,
            }
        groups[key]["standard_mh"] += r.standard_mh
        groups[key]["standard_headcount"] += r.standard_headcount
        groups[key]["final_work_time_hr"] += r.final_work_time_hr
        groups[key]["record_count"] += 1
    return groups


def aggregate_by_line_group(records: list[CalcResult]) -> dict:
    """유사라인 그룹별 집계."""
    groups: dict[str, dict] = {}
    for r in _active_results(records):
        key = _meta(r, "line_group")
        if key not in groups:
            groups[key] = {
                "line_group": key,
                "plant": _meta(r, "plant"),
                "wg": _meta(r, "wg"),
                "standard_mh": 0.0,
                "standard_headcount": 0,
                "final_work_time_hr": 0.0,
                "record_count": 0,
            }
        groups[key]["standard_mh"] += r.standard_mh
        groups[key]["standard_headcount"] += r.standard_headcount
        groups[key]["final_work_time_hr"] += r.final_work_time_hr
        groups[key]["record_count"] += 1
    return groups


def aggregate_by_wg(records: list[CalcResult]) -> dict:
    """W/G별 집계."""
    groups: dict[str, dict] = {}
    for r in _active_results(records):
        key = _meta(r, "wg")
        if key not in groups:
            groups[key] = {
                "wg": key,
                "plant": _meta(r, "plant"),
                "standard_mh": 0.0,
                "standard_headcount": 0,
                "final_work_time_hr": 0.0,
                "record_count": 0,
            }
        groups[key]["standard_mh"] += r.standard_mh
        groups[key]["standard_headcount"] += r.standard_headcount
        groups[key]["final_work_time_hr"] += r.final_work_time_hr
        groups[key]["record_count"] += 1
    return groups


def aggregate_by_plant(records: list[CalcResult]) -> dict:
    """공장별 집계."""
    groups: dict[str, dict] = {}
    for r in _active_results(records):
        key = _meta(r, "plant")
        if key not in groups:
            groups[key] = {
                "plant": key,
                "standard_mh": 0.0,
                "standard_headcount": 0,
                "final_work_time_hr": 0.0,
                "record_count": 0,
            }
        groups[key]["standard_mh"] += r.standard_mh
        groups[key]["standard_headcount"] += r.standard_headcount
        groups[key]["final_work_time_hr"] += r.final_work_time_hr
        groups[key]["record_count"] += 1
    return groups


def calculate_quantitative_record(
    record: QuantitativeRecord,
    rule: RuleMaster,
    freq_db: FrequencyDB,
    calc_unit: Literal["월", "연"] = "월",
    work_hours_per_month: float = 200.0,
    work_hours_per_year: float = 2400.0,
) -> CalcResult:
    """정량 레코드 전체 계산 파이프라인."""
    calc_log: list[str] = []
    allowance_rate = (
        record.allowance_override
        if record.allowance_override is not None
        else rule.default_allowance_rate
    )

    final_freq, method, factors, freq_log, is_overridden = calculate_frequency_by_task_rule(
        rule,
        freq_db,
        record.frequency_override,
    )
    calc_log.extend(freq_log)

    factors.update({
        "plant": record.plant,
        "wg": record.wg,
        "line": record.line or "미지정",
        "line_group": record.line_group or "미지정",
        "judgment_status": record.judgment_status.value,
        "current_headcount": record.current_headcount,
    })

    std_work_time, unit_time_hr, wt_log = calculate_standard_work_time_excel_style(
        record.unit_time_min,
        final_freq,
    )
    calc_log.extend(wt_log)

    final_work_time, allow_log = apply_allowance(std_work_time, allowance_rate)
    calc_log.extend(allow_log)

    standard_mh, standard_md, mh_log = calculate_standard_mh_excel_style(
        final_work_time,
        work_hours_per_month,
        work_hours_per_year,
        calc_unit,
    )
    calc_log.extend(mh_log)

    standard_headcount, standard_headcount_raw, round_log = round_headcount(
        standard_mh,
        rule.rounding_policy,
    )
    calc_log.extend(round_log)

    diff = standard_headcount - record.current_headcount

    return CalcResult(
        record_id=record.record_id,
        auto_frequency=factors.get("auto_frequency", final_freq),
        frequency_method_used=method,
        frequency_factors_used=factors,
        final_frequency=final_freq,
        is_overridden=is_overridden,
        unit_time_hr=unit_time_hr,
        standard_work_time_hr=std_work_time,
        allowance_rate=allowance_rate,
        final_work_time_hr=final_work_time,
        standard_mh=standard_mh,
        standard_md=standard_md,
        standard_headcount_raw=standard_headcount_raw,
        standard_headcount=standard_headcount,
        diff_from_current=diff,
        calc_log=calc_log,
    )
