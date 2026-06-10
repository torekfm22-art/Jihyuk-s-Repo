"""발생빈도 엔진."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from quality_mh.audit_engine import AuditEngine
from quality_mh.constants import RuleStatus, ValidationStatus
from quality_mh.models import FrequencyInput, RuleBase
from quality_mh.rule_loader import load_frequency_rules


class FrequencyEngine:
    def __init__(self, rules: list[RuleBase] | None = None, audit: AuditEngine | None = None) -> None:
        self.rules = rules or load_frequency_rules()
        self.audit = audit or AuditEngine()
        self._rule_map = {r.rule_id: r for r in self.rules}

    def apply_raw_count(self, df: pd.DataFrame) -> pd.DataFrame:
        """Raw 이력 기반 검사건수 집계."""
        rule = self._rule_map.get("FREQ-RAW-COUNT")
        required = ["factory_name", "domain"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            self.audit.log_rule_application(
                "frequency_engine",
                "FREQ-RAW-COUNT",
                status=RuleStatus.NEEDS_REVIEW,
                message=f"필수 컬럼 누락: {missing}",
            )
            return pd.DataFrame()

        group_cols = [c for c in [
            "factory_name", "domain", "inspection_type", "line_name", "inspection_name",
            "year", "month", "product_code", "line_group",
        ] if c in df.columns]

        if "quantity" in df.columns:
            result = df.groupby(group_cols, dropna=False)["quantity"].sum().reset_index()
            result = result.rename(columns={"quantity": "frequency_value"})
        else:
            result = df.groupby(group_cols, dropna=False).size().reset_index(name="frequency_value")

        result["applied_frequency_rule"] = "FREQ-RAW-COUNT"
        result["validation_status"] = ValidationStatus.OK.value
        result["validation_message"] = ""

        self.audit.log_rule_application(
            "frequency_engine",
            "FREQ-RAW-COUNT",
            source_file=rule.source_file if rule else "",
            source_sheet=rule.source_sheet if rule else "",
            status=RuleStatus.CONFIRMED,
            message=f"집계 {len(result)}건",
        )
        return result

    def apply_pivot_pass_through(self, df: pd.DataFrame) -> pd.DataFrame:
        """이미 산출된 pivot frequency 값 사용."""
        rule = self._rule_map.get("FREQ-PASS-THROUGH")
        if "frequency_value" not in df.columns:
            qty_cols = [c for c in df.columns if c in ("quantity", "검사건수", "건수")]
            if qty_cols:
                df = df.copy()
                df["frequency_value"] = df[qty_cols[0]]
            else:
                self.audit.log_rule_application(
                    "frequency_engine",
                    "FREQ-PASS-THROUGH",
                    status=RuleStatus.NEEDS_REVIEW,
                    message="frequency_value 또는 quantity 컬럼 없음",
                )
                return pd.DataFrame()

        result = df.copy()
        result["applied_frequency_rule"] = "FREQ-PASS-THROUGH"
        result["validation_status"] = ValidationStatus.OK.value
        result["validation_message"] = ""

        self.audit.log_rule_application(
            "frequency_engine",
            "FREQ-PASS-THROUGH",
            source_file=rule.source_file if rule else "",
            status=RuleStatus.CONFIRMED,
        )
        return result

    def apply_weighted_average(self, df: pd.DataFrame, value_col: str = "frequency_value") -> pd.DataFrame:
        """2개년 가중평균 - 가중치 미확정 시 NEEDS_REVIEW."""
        rule = self._rule_map.get("FREQ-WEIGHTED-AVG")
        self.audit.log_rule_application(
            "frequency_engine",
            "FREQ-WEIGHTED-AVG",
            source_file=rule.source_file if rule else "",
            status=RuleStatus.RULE_NOT_CONFIRMED,
            message="가중치 미확정 - 단순 평균 placeholder (검토 필요)",
        )

        group_cols = [c for c in ["factory_name", "domain", "inspection_type", "line_name", "month"] if c in df.columns]
        if not group_cols or value_col not in df.columns:
            return pd.DataFrame()

        result = df.groupby(group_cols, dropna=False)[value_col].mean().reset_index()
        result = result.rename(columns={value_col: "frequency_value"})
        result["applied_frequency_rule"] = "FREQ-WEIGHTED-AVG"
        result["validation_status"] = ValidationStatus.RULE_NOT_CONFIRMED.value
        result["validation_message"] = "가중치 미확정 - 산술평균 placeholder"
        return result

    def calc_from_inputs(self, inputs: list[FrequencyInput]) -> pd.DataFrame:
        rows = []
        for inp in inputs:
            if inp.quantity is None:
                rows.append({
                    **inp.model_dump(),
                    "frequency_value": None,
                    "applied_frequency_rule": "",
                    "validation_status": ValidationStatus.MANUAL_CONFIRM_REQUIRED.value,
                    "validation_message": "quantity 미입력",
                })
                continue
            rows.append({
                **inp.model_dump(),
                "frequency_value": inp.quantity,
                "applied_frequency_rule": "FREQ-PASS-THROUGH",
                "validation_status": ValidationStatus.OK.value,
                "validation_message": "",
            })
        return pd.DataFrame(rows)

    def apply_incoming_inspection_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """입고검사 발생빈도 분석(생산계획 연동) 집계 결과 사용."""
        from quality_mh.incoming_frequency_analyzer import to_frequency_dataframe

        rule = self._rule_map.get("FREQ-INCOMING-INSPECTION")
        if df.empty:
            self.audit.log_rule_application(
                "frequency_engine",
                "FREQ-INCOMING-INSPECTION",
                status=RuleStatus.NEEDS_REVIEW,
                message="입고검사 발생빈도 집계 데이터 없음",
            )
            return pd.DataFrame()

        result = to_frequency_dataframe(df)
        if result.empty:
            self.audit.log_rule_application(
                "frequency_engine",
                "FREQ-INCOMING-INSPECTION",
                status=RuleStatus.NEEDS_REVIEW,
                message="입고검사 건수 행 변환 실패",
            )
            return pd.DataFrame()

        self.audit.log_rule_application(
            "frequency_engine",
            "FREQ-INCOMING-INSPECTION",
            source_file=rule.source_file if rule else "",
            source_sheet=rule.source_sheet if rule else "",
            status=RuleStatus.CONFIRMED,
            message=f"입고검사 빈도 {len(result)}건",
        )
        return result

    def process_dataframe(self, df: pd.DataFrame, mode: str = "auto") -> pd.DataFrame:
        """파일 역할에 따라 빈도 산출 방식 선택."""
        if mode == "incoming_summary" or (
            "metric" in df.columns and "inspection_type" in df.columns
        ):
            return self.apply_incoming_inspection_summary(df)
        if mode == "raw" or ("inspection_name" in df.columns and "frequency_value" not in df.columns):
            return self.apply_raw_count(df)
        if "frequency_value" in df.columns or any(c in df.columns for c in ("quantity", "검사건수")):
            return self.apply_pivot_pass_through(df)
        return self.apply_raw_count(df)


def _safe_float(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
