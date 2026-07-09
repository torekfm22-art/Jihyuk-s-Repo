"""Rational Subgroup 검증 — AIAG-VDA subgroup 품질 점검."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

DAY_SHIFT_START_HOUR = 8
DAY_SHIFT_END_HOUR = 20


@dataclass
class SubgroupRationalityResult:
    is_rational: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    invalid_subgroup_ids: list[int] = field(default_factory=list)

    def summary_label(self) -> str:
        if self.is_rational:
            return "Rational Subgroup (OK)"
        return "Invalid Subgroup (Non-rational subgroup)"

    def to_dict(self) -> dict:
        return {
            "is_rational": self.is_rational,
            "violations": self.violations,
            "warnings": self.warnings,
            "invalid_subgroup_ids": self.invalid_subgroup_ids,
            "summary": self.summary_label(),
        }


def _infer_shift(ts: pd.Timestamp) -> str:
    if pd.isna(ts):
        return "UNKNOWN"
    h = ts.hour
    if DAY_SHIFT_START_HOUR <= h < DAY_SHIFT_END_HOUR:
        return "주간"
    return "야간"


def validate_subgroup_rationality(
    sample_df: pd.DataFrame | None,
    *,
    subgroup_size: int | None = None,
) -> SubgroupRationalityResult:
    """
    Subgroup rationality 검증:
    - 동일 LOT (군 내)
    - 동일 시간 구간 (교대·일자 경계 없음)
    - 동일 설비 조건 (line/machine)
    """
    if sample_df is None or sample_df.empty:
        return SubgroupRationalityResult(is_rational=True)

    if "subgroup_id" not in sample_df.columns:
        return SubgroupRationalityResult(is_rational=True)

    violations: list[str] = []
    warnings: list[str] = []
    invalid_ids: list[int] = []

    df = sample_df.copy()
    if "timestamp" in df.columns:
        df["_ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["_ts"] = pd.NaT

    has_lot = "lot" in df.columns
    has_line = "line" in df.columns
    has_machine = "machine" in df.columns

    for sg_id, grp in df.groupby("subgroup_id", sort=True):
        sg_id_int = int(sg_id)
        issues: list[str] = []

        if has_lot:
            lots = grp["lot"].dropna().astype(str).unique()
            if len(lots) > 1:
                issues.append(f"LOT 혼재 ({', '.join(lots[:3])})")

        if has_line:
            lines = grp["line"].dropna().astype(str).unique()
            if len(lines) > 1:
                issues.append(f"라인 혼재 ({', '.join(lines[:3])})")

        if has_machine:
            machines = grp["machine"].dropna().astype(str).unique()
            if len(machines) > 1:
                issues.append(f"설비 혼재 ({', '.join(machines[:3])})")

        if grp["_ts"].notna().any():
            dates = grp["_ts"].dt.date.unique()
            if len(dates) > 1:
                issues.append("일자 경계 교차")

            if "shift" in grp.columns:
                shifts = grp["shift"].dropna().astype(str).unique()
            else:
                shifts = grp["_ts"].apply(_infer_shift).unique()
            if len(shifts) > 1:
                issues.append(f"교대 혼재 ({', '.join(str(s) for s in shifts[:3])})")

            if subgroup_size and len(grp) == subgroup_size:
                span = grp["_ts"].max() - grp["_ts"].min()
                if pd.notna(span) and span.total_seconds() > 8 * 3600:
                    issues.append(f"시간 구간 과다 ({span})")

        if issues:
            invalid_ids.append(sg_id_int)
            violations.append(f"Subgroup #{sg_id_int}: " + "; ".join(issues))

    strategy = str(df["sampling_strategy"].iloc[0]) if "sampling_strategy" in df.columns else ""
    if strategy == "sequence_random":
        warnings.append(
            "순번 랜덤 채취 — LOT·일자 블록 미적용으로 rational subgroup 보장이 약합니다."
        )

    is_rational = len(invalid_ids) == 0 and strategy != "sequence_random"
    if strategy == "sequence_random" and not invalid_ids:
        is_rational = False
        if not violations:
            violations.append("Non-rational sampling strategy (sequence_random fallback)")

    return SubgroupRationalityResult(
        is_rational=is_rational,
        violations=violations,
        warnings=warnings,
        invalid_subgroup_ids=invalid_ids,
    )
