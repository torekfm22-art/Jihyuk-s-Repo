"""USL/LSL 해석 — UI 공차 유형(양측·편측) 반영."""
from __future__ import annotations

import pandas as pd

from src.spc.statistics import SpecType, infer_spec_type

UI_SPEC_MODE_MAP: dict[str, SpecType] = {
    "양측 공차": "two_sided",
    "편측 — 상한치": "upper_only",
    "편측 — 하한치": "lower_only",
}


def ui_spec_mode_to_type(spec_mode: str | None) -> SpecType | None:
    if not spec_mode:
        return None
    return UI_SPEC_MODE_MAP.get(spec_mode)


def _first_numeric_column(df: pd.DataFrame, col: str) -> float | None:
    if col not in df.columns or not df[col].notna().any():
        return None
    return float(df[col].dropna().iloc[0])


def resolve_effective_spec_limits(
    usl: float | None,
    lsl: float | None,
    df: pd.DataFrame,
    *,
    spec_type: SpecType | None = None,
) -> tuple[float | None, float | None, SpecType]:
    """
    분석에 사용할 USL/LSL.

    spec_type이 편측이면 반대쪽 한계는 Excel 컬럼에서 **자동 채우지 않음**.
    (편측 상한 + Excel 하한값 0 → 양측 Cp 산출되는 문제 방지)
    """
    effective_usl = usl
    effective_lsl = lsl

    if spec_type == "upper_only":
        effective_lsl = None
        if effective_usl is None:
            effective_usl = _first_numeric_column(df, "usl")
    elif spec_type == "lower_only":
        effective_usl = None
        if effective_lsl is None:
            effective_lsl = _first_numeric_column(df, "lsl")
    else:
        if effective_usl is None:
            effective_usl = _first_numeric_column(df, "usl")
        if effective_lsl is None:
            effective_lsl = _first_numeric_column(df, "lsl")
        if spec_type is None:
            spec_type = infer_spec_type(effective_usl, effective_lsl)
        return effective_usl, effective_lsl, spec_type

    if spec_type is None:
        spec_type = infer_spec_type(effective_usl, effective_lsl)
    return effective_usl, effective_lsl, spec_type
