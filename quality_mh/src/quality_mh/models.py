"""품질 M/H 분석 시스템 Pydantic 데이터 모델."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel


class FrequencyMethod(str, Enum):
    WEIGHTED_AVG = "3개년가중평균"
    PLAN_LINKED = "생산계획연동"
    PERIODIC = "수행주기"


class RoundingPolicy(str, Enum):
    CEIL = "일반올림"
    STANDARD = "표준공수올림법"
    EVEN_SHIFT = "주야교대짝수"
    MANUAL = "수동조정"


class TaskType(str, Enum):
    QUANTITATIVE = "정량"
    QUALITATIVE = "정성"
    NON_STANDARD = "표준외"


class JudgmentStatus(str, Enum):
    CONFIRMED = "확정"
    ADJUSTED = "조정"
    RECLASSIFIED = "재분류"
    ADDED = "추가"
    EXCLUDED = "제외"


class RuleMaster(BaseModel):
    task_code: str
    wg: str
    task_name: str
    task_type: TaskType
    unit_time_method: str
    frequency_method: FrequencyMethod
    default_allowance_rate: float = 0.10
    rounding_policy: RoundingPolicy = RoundingPolicy.STANDARD


class FrequencyDB(BaseModel):
    task_code: str
    frequency_method: FrequencyMethod
    product_group: Optional[str] = None
    line: Optional[str] = None
    # 3개년 가중평균용
    y1_actual: Optional[float] = None
    y2_actual: Optional[float] = None
    y3_actual: Optional[float] = None
    weight1: float = 5.0
    weight2: float = 3.0
    weight3: float = 2.0
    # 생산계획 연동용
    ref_ratio: Optional[float] = None
    plan_qty: Optional[float] = None
    sampling_type: Optional[Literal["샘플링", "전수"]] = None
    # 수행주기용
    cycle_type: Optional[Literal["일간", "주간", "월간", "분기", "연간"]] = None
    cycle_count: Optional[float] = None
    working_days: float = 20.0
    working_weeks: float = 4.0
    working_months: float = 12.0
    data_source: Optional[str] = None
    description: Optional[str] = None


class QuantitativeRecord(BaseModel):
    record_id: str
    plant: str
    wg: str
    task_code: str
    task_name: str
    sub_task: Optional[str] = None
    line: Optional[str] = None
    line_group: Optional[str] = None
    performers: float = 1.0
    unit_time_min: float
    current_headcount: float = 0.0
    frequency_override: Optional[float] = None
    allowance_override: Optional[float] = None
    judgment_status: JudgmentStatus = JudgmentStatus.CONFIRMED
    remark: Optional[str] = None
    hq_review: Optional[str] = None
    estimation_method: Optional[str] = None  # 모답스, 관측법, 업무기준, 동작모듈화
    frequency_method_text: Optional[str] = None
    cycle_type: Optional[str] = None
    cycle_count: Optional[float] = None
    data_source: Optional[str] = None
    mh_formula: Optional[str] = None
    annual_frequency: Optional[float] = None


class CalcResult(BaseModel):
    record_id: str
    auto_frequency: float
    frequency_method_used: FrequencyMethod
    frequency_factors_used: dict
    final_frequency: float
    is_overridden: bool
    unit_time_hr: float
    standard_work_time_hr: float
    allowance_rate: float
    final_work_time_hr: float
    standard_mh: float
    standard_md: float
    standard_headcount_raw: float
    standard_headcount: int
    diff_from_current: float
    calc_log: list[str]


class QualitativeRecord(BaseModel):
    record_id: str
    plant: str
    wg: str
    task_name: str
    task_definition: Optional[str] = None
    workload_desc: Optional[str] = None
    standard_headcount: int = 0
    current_headcount: int = 0
    diff: int = 0
    selection_reason: Optional[str] = None
    future_criteria: Optional[str] = None
    remark: Optional[str] = None
