"""검증용 샘플 데이터."""
from __future__ import annotations

from quality_mh.models import FrequencyDB, FrequencyMethod, QuantitativeRecord, RuleMaster
from quality_mh.rule_master import get_rule_by_task_code


def scenario_1_weighted_avg() -> tuple[QuantitativeRecord, RuleMaster, FrequencyDB]:
    """입고/정기점검 (IN-001) - 3개년 가중평균."""
    rule = get_rule_by_task_code("IN-001")
    assert rule is not None
    freq_db = FrequencyDB(
        task_code="IN-001",
        frequency_method=FrequencyMethod.WEIGHTED_AVG,
        y1_actual=120.0,
        y2_actual=100.0,
        y3_actual=80.0,
        weight1=5.0,
        weight2=3.0,
        weight3=2.0,
    )
    record = QuantitativeRecord(
        record_id="R-SC1",
        plant="김천",
        wg="입고",
        task_code="IN-001",
        task_name="정기 점검",
        unit_time_min=30.0,
        current_headcount=0.0,
    )
    return record, rule, freq_db


def scenario_2_plan_linked() -> tuple[QuantitativeRecord, RuleMaster, FrequencyDB]:
    """완성/최종검사 (FI-001) - 생산계획 연동."""
    rule = get_rule_by_task_code("FI-001")
    assert rule is not None
    freq_db = FrequencyDB(
        task_code="FI-001",
        frequency_method=FrequencyMethod.PLAN_LINKED,
        ref_ratio=0.02,
        plan_qty=50000.0,
    )
    record = QuantitativeRecord(
        record_id="R-SC2",
        plant="김천",
        wg="완성",
        task_code="FI-001",
        task_name="최종 검사",
        unit_time_min=5.0,
        current_headcount=0.0,
    )
    return record, rule, freq_db


def scenario_3_periodic() -> tuple[QuantitativeRecord, RuleMaster, FrequencyDB]:
    """공통/품질미팅 (CM-001) - 수행주기."""
    rule = get_rule_by_task_code("CM-001")
    assert rule is not None
    freq_db = FrequencyDB(
        task_code="CM-001",
        frequency_method=FrequencyMethod.PERIODIC,
        cycle_type="주간",
        cycle_count=2.0,
        working_weeks=4.0,
    )
    record = QuantitativeRecord(
        record_id="R-SC3",
        plant="김천",
        wg="공통",
        task_code="CM-001",
        task_name="품질 미팅",
        unit_time_min=60.0,
        current_headcount=0.0,
    )
    return record, rule, freq_db


def build_all_scenarios() -> list[tuple[QuantitativeRecord, RuleMaster, FrequencyDB]]:
    return [scenario_1_weighted_avg(), scenario_2_plan_linked(), scenario_3_periodic()]


def build_demo_frequency_df():
    """레거시 테스트 호환용."""
    import pandas as pd

    return pd.DataFrame([
        {"factory_name": "김천", "domain": "공정", "inspection_type": "순회검사",
         "line_name": "라인A", "quantity": 120},
    ])


def build_demo_unit_time_df():
    """레거시 테스트 호환용."""
    import pandas as pd

    return pd.DataFrame([
        {"factory_name": "김천", "line_name": "라인A", "mod_value": 5.0, "auxiliary_rate": 0.10},
    ])
