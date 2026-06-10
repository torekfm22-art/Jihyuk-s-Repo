"""결과 엑셀 출력."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from quality_mh.audit_engine import AuditEngine
from quality_mh.rule_loader import (
    load_frequency_rules,
    load_manpower_rules,
    load_unit_time_rules,
)


def rules_to_dataframe(rules) -> pd.DataFrame:
    return pd.DataFrame([r.model_dump() for r in rules])


def build_output_workbook(data: dict[str, pd.DataFrame]) -> BytesIO:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        sheet_order = [
            ("표준 마스터", "standard_master"),
            ("파일 분석 결과", "file_analysis"),
            ("발생빈도 산출", "frequency"),
            ("단위시간 산출", "unit_time"),
            ("MH 산출 결과", "mh_results"),
            ("라인별 집계", "line_aggregate"),
            ("공정별 집계", "process_aggregate"),
            ("표준 인원 환산", "manpower"),
            ("적용 rule 목록", "applied_rules"),
            ("검토 필요 항목", "review_items"),
            ("원본 정규화 데이터", "normalized_raw"),
            ("계산 로그", "calculation_logs"),
        ]
        for sheet_name, key in sheet_order:
            df = data.get(key, pd.DataFrame())
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                pd.DataFrame({"message": ["데이터 없음"]}).to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    buffer.seek(0)
    return buffer


def prepare_output_data(
    *,
    standard_master_df: pd.DataFrame,
    file_analysis_df: pd.DataFrame,
    frequency_df: pd.DataFrame,
    unit_time_df: pd.DataFrame,
    mh_df: pd.DataFrame,
    line_agg_df: pd.DataFrame,
    process_agg_df: pd.DataFrame,
    manpower_df: pd.DataFrame,
    normalized_raw_df: pd.DataFrame,
    audit: AuditEngine,
) -> dict[str, pd.DataFrame]:
    audit_dfs = audit.to_dataframes_dict()
    applied_rules = pd.concat(
        [
            rules_to_dataframe(load_frequency_rules()).assign(engine="frequency"),
            rules_to_dataframe(load_unit_time_rules()).assign(engine="unit_time"),
            rules_to_dataframe(load_manpower_rules()).assign(engine="manpower"),
        ],
        ignore_index=True,
    )
    return {
        "standard_master": standard_master_df,
        "file_analysis": file_analysis_df,
        "frequency": frequency_df,
        "unit_time": unit_time_df,
        "mh_results": mh_df,
        "line_aggregate": line_agg_df,
        "process_aggregate": process_agg_df,
        "manpower": manpower_df,
        "applied_rules": applied_rules,
        "review_items": audit_dfs["review_items"],
        "normalized_raw": normalized_raw_df,
        "calculation_logs": audit_dfs["calculation_logs"],
    }


def save_output_excel(path: Path, data: dict[str, pd.DataFrame]) -> Path:
    buffer = build_output_workbook(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())
    return path
