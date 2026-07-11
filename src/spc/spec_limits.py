"""USL/LSL 해석 — UI 공차 유형(양측·편측) 반영."""
from __future__ import annotations

import pandas as pd

from src.spc.statistics import SpecType, infer_spec_type
from src.spc.characteristic_split import normalize_split_value

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


def _is_non_numeric_spec_value(val: object) -> bool:
    if val is None:
        return False
    try:
        if isinstance(val, float) and pd.isna(val):
            return False
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "-", "—"):
        return False
    try:
        float(s.replace(",", ""))
        return False
    except ValueError:
        return True


def _count_mixed_spec_column(series: pd.Series) -> tuple[int, bool]:
    """Returns (distinct_numeric_count, has_non_numeric)."""
    raw = series.dropna()
    if raw.empty:
        return 0, False
    has_text = bool(raw.apply(_is_non_numeric_spec_value).any())
    nums = pd.to_numeric(raw, errors="coerce").dropna()
    n_distinct = int(nums.nunique()) if not nums.empty else 0
    return n_distinct, has_text


def assess_group_spec_quality(
    subset: pd.DataFrame,
    *,
    lsl: float | None,
    usl: float | None,
    spec_type: SpecType | None = None,
) -> tuple[bool, str, list[str]]:
    """
    그룹별 자동 규격 품질 평가.
    Returns: (warn, status_label, issue_codes)
    """
    issues: list[str] = []
    for col, label in (("usl", "USL"), ("lsl", "LSL")):
        if col not in subset.columns:
            continue
        n_distinct, has_text = _count_mixed_spec_column(subset[col])
        if has_text:
            issues.append(f"{label} 텍스트")
        if n_distinct > 1:
            issues.append(f"{label} 혼재")

    if lsl is None and usl is None:
        issues.append("미감지")
    elif lsl is not None and usl is not None:
        try:
            if float(lsl) >= float(usl):
                issues.append("LSL≥USL")
        except (TypeError, ValueError):
            issues.append("비수치")

    resolved = spec_type or infer_spec_type(usl, lsl)
    if resolved == "upper_only" and usl is None:
        issues.append("USL 없음")
    if resolved == "lower_only" and lsl is None:
        issues.append("LSL 없음")

    if not issues:
        return False, "OK", []
    if "미감지" in issues:
        return True, "미감지", issues
    return True, "⚠ 확인", issues


def assess_spec_values_quality(
    lsl: float | None,
    usl: float | None,
) -> tuple[bool, str, list[str]]:
    """편집 후 단일 행 규격값 재평가."""
    issues: list[str] = []
    for label, val in (("LSL", lsl), ("USL", usl)):
        if val is None:
            continue
        try:
            if isinstance(val, float) and pd.isna(val):
                continue
            float(val)
        except (TypeError, ValueError):
            issues.append(f"{label} 비수치")
    if lsl is None and usl is None:
        issues.append("미감지")
    elif lsl is not None and usl is not None:
        try:
            if float(lsl) >= float(usl):
                issues.append("LSL≥USL")
        except (TypeError, ValueError):
            pass
    if not issues:
        return False, "OK", []
    if "미감지" in issues:
        return True, "미감지", issues
    return True, "⚠ 확인", issues


SPEC_WARN_FILL = "#ffe4ec"


def resolve_subset_spec_limits(
    df: pd.DataFrame,
    *,
    spec_type: SpecType | None = None,
) -> tuple[float | None, float | None, SpecType]:
    """분리 그룹(부분 DataFrame)에서 USL/LSL 추출 — UI 전역값 미사용."""
    return resolve_effective_spec_limits(None, None, df, spec_type=spec_type)


def preview_group_spec_limits(
    df: pd.DataFrame,
    split_col: str,
    split_values: list[str],
    *,
    spec_type: SpecType | None = None,
    max_rows: int = 80,
) -> list[dict]:
    """분리 그룹별 LSL/USL 미리보기 (데이터 입력 UI용)."""
    if not split_values:
        return []

    label_by_norm = {normalize_split_value(v): str(v) for v in split_values}
    wanted = set(label_by_norm.keys())
    if not wanted:
        return []

    work = df
    norm_series = work[split_col].apply(normalize_split_value)  # type: ignore[index]
    rows: list[dict] = []
    for norm_val, subset in work.groupby(norm_series, sort=False):
        if norm_val not in wanted:
            continue
        usl, lsl, resolved = resolve_subset_spec_limits(subset, spec_type=spec_type)
        warn, status, issues = assess_group_spec_quality(
            subset, lsl=lsl, usl=usl, spec_type=resolved,
        )
        rows.append({
            "그룹": label_by_norm.get(norm_val, str(norm_val)),
            "LSL": lsl,
            "USL": usl,
            "공차유형": resolved,
            "행수": len(subset),
            "warn": warn,
            "상태": status,
            "issues": issues,
        })
        if len(rows) >= max_rows:
            break

    order = {normalize_split_value(v): i for i, v in enumerate(split_values)}
    rows.sort(key=lambda r: order.get(normalize_split_value(r["그룹"]), 9999))
    return rows
