"""MH = 발생빈도 × 단위시간 집계 엔진."""
from __future__ import annotations

import pandas as pd

from quality_mh.audit_engine import AuditEngine
from quality_mh.constants import ValidationStatus
from quality_mh.models import MhResult


class MhEngine:
    def __init__(self, audit: AuditEngine | None = None) -> None:
        self.audit = audit or AuditEngine()

    @staticmethod
    def _merge_keys() -> list[str]:
        return ["factory_name", "domain", "line_name", "inspection_type", "inspection_name", "task_name"]

    def calc_mh(
        self,
        frequency_df: pd.DataFrame,
        unit_time_df: pd.DataFrame,
    ) -> pd.DataFrame:
        freq = frequency_df.copy()
        ut = unit_time_df.copy()

        if "inspection_name" not in freq.columns and "task_name" in freq.columns:
            freq["inspection_name"] = freq["task_name"]
        if "task_name" not in freq.columns and "inspection_name" in freq.columns:
            freq["task_name"] = freq["inspection_name"]

        merge_cols = [c for c in self._merge_keys() if c in freq.columns and c in ut.columns]
        if not merge_cols:
            merge_cols = [c for c in ["factory_name", "line_name", "inspection_name"] if c in freq.columns and c in ut.columns]

        if not merge_cols:
            self.audit.log_calculation(
                "mh_merge",
                "mh_engine",
                status=ValidationStatus.NEEDS_REVIEW,
                message="빈도/단위시간 병합 키 없음",
            )
            return pd.DataFrame()

        merged = pd.merge(freq, ut, on=merge_cols, how="outer", suffixes=("_freq", "_ut"))

        freq_col = "frequency_value"
        ut_col = "unit_time_min" if "unit_time_min" in merged.columns else "unit_time_value"

        results = []
        for _, row in merged.iterrows():
            fv = row.get(freq_col)
            uv = row.get(ut_col)
            status = ValidationStatus.OK
            message = ""

            if pd.isna(fv) or fv is None:
                status = ValidationStatus.MANUAL_CONFIRM_REQUIRED
                message = "발생빈도 없음"
                mh = None
            elif pd.isna(uv) or uv is None:
                status = ValidationStatus.MANUAL_CONFIRM_REQUIRED
                message = "단위시간 없음"
                mh = None
            else:
                mh = float(fv) * float(uv)

            result = MhResult(
                factory_name=str(row.get("factory_name", "")),
                domain=str(row.get("domain", "")),
                line_name=str(row.get("line_name", "")),
                inspection_type=str(row.get("inspection_type", "")),
                task_name=str(row.get("task_name") or row.get("inspection_name", "")),
                frequency_value=None if pd.isna(fv) else float(fv),
                unit_time_value=None if pd.isna(uv) else float(uv),
                mh_value=mh,
                applied_frequency_rule=str(row.get("applied_frequency_rule", "")),
                applied_unit_time_rule=",".join(
                    str(x) for x in (row.get("applied_rules") or []) if x
                ) if "applied_rules" in row else str(row.get("applied_unit_time_rule", "")),
                validation_status=status,
                validation_message=message,
            )
            results.append(result)

        self.audit.collect_review_from_mh(results)
        df_out = pd.DataFrame([r.model_dump() for r in results])

        self.audit.log_calculation(
            "mh_calc",
            "mh_engine",
            input_summary=f"freq={len(freq)}, ut={len(ut)}",
            output_summary=f"mh={len(df_out)}",
            status=ValidationStatus.OK,
        )
        return df_out

    def aggregate_by_line(self, mh_df: pd.DataFrame) -> pd.DataFrame:
        if mh_df.empty or "mh_value" not in mh_df.columns:
            return pd.DataFrame()
        group_cols = [c for c in ["factory_name", "line_name", "domain"] if c in mh_df.columns]
        agg = mh_df.groupby(group_cols, dropna=False)["mh_value"].sum().reset_index()
        agg = agg.rename(columns={"mh_value": "total_mh"})
        return agg

    def aggregate_by_process(self, mh_df: pd.DataFrame) -> pd.DataFrame:
        if mh_df.empty or "mh_value" not in mh_df.columns:
            return pd.DataFrame()
        process_col = "domain" if "domain" in mh_df.columns else "inspection_type"
        group_cols = [c for c in ["factory_name", process_col, "inspection_type"] if c in mh_df.columns]
        agg = mh_df.groupby(group_cols, dropna=False)["mh_value"].sum().reset_index()
        agg = agg.rename(columns={"mh_value": "total_mh"})
        return agg
