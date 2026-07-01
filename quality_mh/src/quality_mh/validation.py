"""입력값 검증 로직."""
from __future__ import annotations

import warnings
from typing import Optional

from quality_mh.models import FrequencyDB, FrequencyMethod, QuantitativeRecord, RuleMaster


class ValidationError(Exception):
    """입력 검증 오류."""


class ValidationWarning(UserWarning):
    """입력 검증 경고."""


def validate_record(
    record: QuantitativeRecord,
    rule: RuleMaster,
    freq_db: Optional[FrequencyDB],
) -> dict:
    """
    정량 레코드 검증.
    오류 시 ValidationError, 경고 시 warnings.warn 반환 dict에 override_diff_rate 포함.
    """
    issues: list[str] = []
    meta: dict = {}

    if not record.record_id:
        issues.append("record_id가 비어 있습니다.")
    if not record.plant:
        issues.append("공장(plant)이 비어 있습니다.")
    if not record.wg:
        issues.append("W/G가 비어 있습니다.")
    if not record.task_code:
        issues.append("업무 코드(task_code)가 비어 있습니다.")
    if not record.task_name:
        issues.append("업무 항목명이 비어 있습니다.")

    if record.unit_time_min is None or record.unit_time_min <= 0:
        issues.append("단위시간은 0보다 커야 합니다.")

    for field_name, value in [
        ("performers", record.performers),
        ("current_headcount", record.current_headcount),
        ("unit_time_min", record.unit_time_min),
    ]:
        if value is not None and value < 0:
            issues.append(f"{field_name}에 음수값이 입력되었습니다.")

    if record.frequency_override is not None and record.frequency_override < 0:
        issues.append("발생빈도 override에 음수값이 입력되었습니다.")

    if record.allowance_override is not None and record.allowance_override < 0:
        issues.append("부가공수 override에 음수값이 입력되었습니다.")

    if rule is None:
        issues.append("업무 항목이 rule master에 없습니다.")
    elif rule.task_code != record.task_code:
        issues.append(f"rule master 코드({rule.task_code})와 레코드 코드({record.task_code})가 불일치합니다.")

    if freq_db is None:
        warnings.warn(
            f"업무 '{record.task_code}'의 발생빈도 DB row가 없습니다.",
            ValidationWarning,
            stacklevel=2,
        )
        meta["freq_db_missing"] = True
    elif rule is not None and freq_db is not None:
        if record.frequency_override is not None and record.frequency_override > 0:
            pass  # 발생빈도 직접 입력 시 DB 자동 산출 필드 검증 생략
        else:
            method = freq_db.frequency_method
            if method == FrequencyMethod.WEIGHTED_AVG:
                if (
                    freq_db.y1_actual is None
                    and freq_db.y2_actual is None
                    and freq_db.y3_actual is None
                ):
                    issues.append("3개년 가중평균: Y-1/Y-2/Y-3 실적이 모두 없습니다.")
                elif any(
                    v is None for v in (freq_db.y1_actual, freq_db.y2_actual, freq_db.y3_actual)
                ):
                    warnings.warn(
                        f"업무 '{record.task_code}': 일부 연도 실적이 누락되었습니다.",
                        ValidationWarning,
                        stacklevel=2,
                    )
            elif method == FrequencyMethod.PLAN_LINKED:
                if freq_db.ref_ratio is None or freq_db.plan_qty is None:
                    issues.append("생산계획 연동: ref_ratio 또는 plan_qty가 없습니다.")
            elif method == FrequencyMethod.PERIODIC:
                if freq_db.cycle_type is None or freq_db.cycle_count is None:
                    issues.append("수행주기: cycle_type 또는 cycle_count가 없습니다.")

    if issues:
        raise ValidationError("; ".join(issues))

    if record.frequency_override is not None and freq_db is not None and rule is not None:
        from quality_mh.frequency_engine import calculate_frequency_by_task_rule

        auto_freq, _, factors, _, _ = calculate_frequency_by_task_rule(
            rule, freq_db, record.frequency_override,
        )
        if auto_freq != 0:
            meta["override_diff_rate"] = (record.frequency_override - auto_freq) / auto_freq
        meta["auto_frequency"] = auto_freq
        meta["override_value"] = record.frequency_override

    return meta
