"""Pydantic 데이터 모델."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from quality_mh.constants import RuleStatus, ValidationStatus


class RuleBase(BaseModel):
    rule_id: str
    revision: str = "1.0"
    category: str
    sub_category: str = ""
    applicable_factory: list[str] = Field(default_factory=lambda: ["*"])
    applicable_line: list[str] = Field(default_factory=lambda: ["*"])
    formula_expression: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    source_file: str = ""
    source_sheet: str = ""
    source_range: str = ""
    status: RuleStatus = RuleStatus.NEEDS_REVIEW
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    verified_by: str = ""
    remarks: str = ""


class StandardTask(BaseModel):
    standard_id: str
    revision: str = "1.0"
    task_type: str  # 정량 / 정성
    major_category: str
    middle_category: str = ""
    sub_task: str = ""
    description: str = ""
    source_note: str = ""
    status: RuleStatus = RuleStatus.SOURCE_NOT_VERIFIED


class FrequencyInput(BaseModel):
    factory_name: str
    year: int | None = None
    month: int | None = None
    domain: str
    inspection_type: str = ""
    line_group: str = ""
    line_name: str = ""
    product_code: str = ""
    product_name: str = ""
    quantity: float | None = None
    source_file: str = ""
    source_sheet: str = ""


class UnitTimeInput(BaseModel):
    factory_name: str
    line_name: str = ""
    inspection_name: str = ""
    movement_distance_m: float | None = None
    weight_kg: float | None = None
    cart_flag: bool = False
    mod_code: str = ""
    mod_value: float | None = None
    measured_wait_sec: float | None = None
    auxiliary_rate: float | None = None
    source_file: str = ""
    source_sheet: str = ""


class MhResult(BaseModel):
    factory_name: str
    domain: str
    line_name: str = ""
    inspection_type: str = ""
    task_name: str = ""
    frequency_value: float | None = None
    unit_time_value: float | None = None
    mh_value: float | None = None
    applied_frequency_rule: str = ""
    applied_unit_time_rule: str = ""
    validation_status: ValidationStatus = ValidationStatus.NEEDS_REVIEW
    validation_message: str = ""


class ManpowerResult(BaseModel):
    factory_name: str
    line_name: str = ""
    total_mh: float | None = None
    manpower_formula: str = ""
    standard_headcount: float | None = None
    status: RuleStatus = RuleStatus.RULE_NOT_CONFIRMED
    message: str = ""


class AuditEntry(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    engine: str
    rule_id: str = ""
    source_file: str = ""
    source_sheet: str = ""
    source_range: str = ""
    action: str
    status: RuleStatus | ValidationStatus = RuleStatus.NEEDS_REVIEW
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class FileAnalysisResult(BaseModel):
    file_name: str
    factory_name: str = ""
    file_role: str = "미분류"
    sheet_names: list[str] = Field(default_factory=list)
    detected_columns: dict[str, list[str]] = Field(default_factory=dict)
    status: ValidationStatus = ValidationStatus.NEEDS_REVIEW
    message: str = ""


class CalculationLog(BaseModel):
    step: str
    engine: str
    input_summary: str = ""
    output_summary: str = ""
    rule_id: str = ""
    status: ValidationStatus = ValidationStatus.OK
    message: str = ""
