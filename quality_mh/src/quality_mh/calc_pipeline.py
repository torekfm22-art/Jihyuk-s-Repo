"""계산 파이프라인 (공장 설정 반영)."""
from __future__ import annotations

from quality_mh.calculation_engine import calculate_quantitative_record
from quality_mh.database import save_calc_result
from quality_mh.frequency_engine import calculate_frequency_by_task_rule
from quality_mh.models import CalcResult, FrequencyDB, QuantitativeRecord, RoundingPolicy
from quality_mh.plant_config import PlantConfig
from quality_mh.rule_master import RuleMasterRegistry
from quality_mh.validation import ValidationError, validate_record


def run_calculation_pipeline(
    records: list[QuantitativeRecord],
    registry: RuleMasterRegistry,
    freq_db_list: list[FrequencyDB],
    config: PlantConfig,
) -> list[CalcResult]:
    """전체 정량 레코드 재계산."""
    freq_map = {f.task_code: f for f in freq_db_list}
    params = config.calc_params()
    policy = config.effective_rounding_policy()
    results: list[CalcResult] = []

    for record in records:
        rule = registry.get_by_task_code(record.task_code)
        freq_db = freq_map.get(record.task_code)
        if not rule or not freq_db:
            continue
        try:
            validate_record(record, rule, freq_db)
            rule_copy = rule.model_copy(update={"rounding_policy": policy})
            allowance = (
                record.allowance_override
                if record.allowance_override is not None
                else config.allowance_rate
            )
            record_copy = record.model_copy()
            override = record.frequency_override if record.frequency_override is not None else record.annual_frequency
            if override is not None and override > 0:
                record_copy.frequency_override = override

            result = calculate_quantitative_record(
                record_copy,
                rule_copy,
                freq_db,
                calc_unit="연",
                work_hours_per_month=params["work_hours_per_month"],
                work_hours_per_year=params["work_hours_per_year"],
            )
            if allowance != rule.default_allowance_rate:
                from quality_mh.calculation_engine import apply_allowance, calculate_standard_mh_excel_style, round_headcount
                std_time = result.standard_work_time_hr
                final_time, _ = apply_allowance(std_time, allowance)
                mh, md, _ = calculate_standard_mh_excel_style(
                    final_time,
                    params["work_hours_per_month"],
                    params["work_hours_per_year"],
                    "연",
                )
                hc, raw, _ = round_headcount(mh, policy)
                result = result.model_copy(update={
                    "allowance_rate": allowance,
                    "final_work_time_hr": final_time,
                    "standard_mh": mh,
                    "standard_md": md,
                    "standard_headcount": hc,
                    "standard_headcount_raw": raw,
                    "diff_from_current": hc - record.current_headcount,
                })
            results.append(result)
            save_calc_result(result)
        except ValidationError:
            continue
    return results
