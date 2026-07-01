"""M/H 산출 Tool 계산 엔진."""
from __future__ import annotations

from typing import Any

from quality_mh.calculation_engine import calculate_quantitative_record
from quality_mh.frequency_engine import calculate_frequency_weighted_average_excel_style
from quality_mh.method_table import MethodTableEntry, UNIT_TIME_METHOD_DESC
from quality_mh.models import CalcResult, FrequencyDB, FrequencyMethod, QuantitativeRecord, RuleMaster
from quality_mh.plan_linked_frequency import (
    calc_fg_style_plan_linked_frequency,
    calc_simple_plan_linked_frequency,
)
from quality_mh.plant_config import PlantConfig
from quality_mh.rule_master import RuleMasterRegistry


FG_STYLE_TASKS = {
    "완성품 검사",
    "성능 검사",
    "최종 검사",
    "상품류 검사",
    "CKD/KD 검사",
}


def unit_time_method_guide(method: str) -> str:
    return UNIT_TIME_METHOD_DESC.get(method, f"{method} — 현재는 직접 기입")


def resolve_rule(registry: RuleMasterRegistry, entry: MethodTableEntry) -> RuleMaster | None:
    return registry.get_by_wg_and_task_name(entry.wg, entry.task_name)


def calc_mh_tool_result(
    *,
    entry: MethodTableEntry,
    rule: RuleMaster,
    config: PlantConfig,
    unit_time_min: float,
    freq_inputs: dict[str, Any],
) -> tuple[float, list[str], dict[str, Any], CalcResult]:
    """단위시간·발생빈도 산출 후 M/H 계산."""
    calc_log: list[str] = []
    calc_log.append(f"[업무] {entry.wg} · {entry.task_name}")
    calc_log.append(f"[단위시간 산정] {entry.unit_time_method} — 직접기입 {unit_time_min}분")

    freq_method = entry.frequency_method
    factors: dict[str, Any] = {"unit_time_method": entry.unit_time_method}
    frequency = 0.0

    if freq_method == "3개년 가중평균":
        y1 = float(freq_inputs["y1"])
        y2 = float(freq_inputs["y2"])
        y3 = float(freq_inputs["y3"])
        w1 = float(freq_inputs.get("w1", 5.0))
        w2 = float(freq_inputs.get("w2", 3.0))
        w3 = float(freq_inputs.get("w3", 2.0))
        calc_log.append("[발생빈도] 3개년 가중평균")
        frequency, sub_factors, sub_log = calculate_frequency_weighted_average_excel_style(
            y1, y2, y3, w1, w2, w3
        )
        factors.update(sub_factors)
        calc_log.extend(sub_log)
        freq_db = FrequencyDB(
            task_code=rule.task_code,
            frequency_method=FrequencyMethod.WEIGHTED_AVG,
            y1_actual=y1,
            y2_actual=y2,
            y3_actual=y3,
            weight1=w1,
            weight2=w2,
            weight3=w3,
        )

    elif freq_method == "생산계획 연동":
        calc_log.append("[발생빈도] 생산계획 연동 (FG expected qty 양식)")
        use_fg = bool(freq_inputs.get("use_fg_style", entry.task_name in FG_STYLE_TASKS))
        if use_fg and freq_inputs.get("prior_monthly_by_product"):
            prior_by_product: dict[str, list[float]] = freq_inputs["prior_monthly_by_product"]
            prior_prod = freq_inputs.get("prior_monthly_production", [0.0] * 12)
            ratio_months = freq_inputs.get("ratio_months")
            frequency, sub_factors, sub_log = calc_fg_style_plan_linked_frequency(
                prior_monthly_inspection_by_product=prior_by_product,
                prior_monthly_production=prior_prod,
                forecast_monthly_production=config.monthly_production,
                ratio_months=int(ratio_months) if ratio_months else None,
            )
        else:
            prior_ins = float(freq_inputs.get("prior_inspection_total", 0))
            prior_prod = float(freq_inputs.get("prior_production_total", 0))
            frequency, sub_factors, sub_log = calc_simple_plan_linked_frequency(
                prior_ins,
                prior_prod,
                config.annual_production,
            )
        factors.update(sub_factors)
        calc_log.extend(sub_log)
        freq_db = FrequencyDB(
            task_code=rule.task_code,
            frequency_method=FrequencyMethod.PLAN_LINKED,
            ref_ratio=sub_factors.get("ref_ratio"),
            plan_qty=config.annual_production,
        )

    else:
        raise ValueError(f"M/H 산출 Tool에서 지원하지 않는 발생빈도 방식: {freq_method}")

    record = QuantitativeRecord(
        record_id="TOOL-PREVIEW",
        plant=config.plant_name,
        wg=entry.wg,
        task_code=rule.task_code,
        task_name=entry.task_name,
        unit_time_min=unit_time_min,
        annual_frequency=frequency,
        frequency_override=frequency,
        estimation_method=entry.unit_time_method,
        frequency_method_text=freq_method,
    )

    rule_copy = rule.model_copy(update={"rounding_policy": config.effective_rounding_policy()})
    params = config.calc_params()
    result = calculate_quantitative_record(
        record,
        rule_copy,
        freq_db,
        calc_unit="연",
        work_hours_per_month=params["work_hours_per_month"],
        work_hours_per_year=params["work_hours_per_year"],
    )
    calc_log.extend(result.calc_log)
    factors["annual_frequency"] = frequency
    return frequency, calc_log, factors, result
