"""필터 후 원본 데이터에서 채취 표본 행 매칭."""
from __future__ import annotations

import numpy as np
import pandas as pd
_SAMPLING_META_COLUMNS = frozenset({
    "subgroup_id",
    "sampling_block",
    "sampling_date",
    "sampling_strategy",
    "sampling_boundary",
    "seq_start_index",
    "sampling_hour_bucket",
    "imr_sampling_unit",
    "original_index",
})


def _match_columns(filtered_df: pd.DataFrame, sample_df: pd.DataFrame) -> list[str]:
    skip = _SAMPLING_META_COLUMNS | {
        c for c in sample_df.columns if str(c).startswith("_")
    }
    cols = [
        str(c)
        for c in sample_df.columns
        if c not in skip and str(c) in filtered_df.columns
    ]
    if cols:
        return cols
    for c in ("timestamp", "value", "lot", "machine", "characteristic"):
        if c in filtered_df.columns and c in sample_df.columns:
            cols.append(c)
    return cols


def align_sampled_mask(mask, length: int) -> pd.Series:
    """표시용 0..n-1 길이 bool Series (ndarray·Series 모두 허용)."""
    if isinstance(mask, pd.Series):
        values = mask.to_numpy(dtype=bool, copy=False)
    else:
        values = np.asarray(mask, dtype=bool)
    if len(values) != length:
        aligned = np.zeros(length, dtype=bool)
        n = min(length, len(values))
        if n:
            aligned[:n] = values[:n]
        values = aligned
    return pd.Series(values)


def build_sampled_row_mask(
    filtered_df: pd.DataFrame | None,
    sample_df: pd.DataFrame | None,
) -> pd.Series:
    """filtered_df 행 중 sample_df에 포함된 행 True."""
    if filtered_df is None or filtered_df.empty:
        return pd.Series(dtype=bool)
    if sample_df is None or sample_df.empty:
        return pd.Series(False, index=filtered_df.index)

    if "original_index" in sample_df.columns:
        orig = pd.to_numeric(sample_df["original_index"], errors="coerce").dropna().astype(int)
        mask = pd.Series(filtered_df.index.isin(orig.unique()), index=filtered_df.index)
        if bool(mask.any()):
            return mask

    match_cols = _match_columns(filtered_df, sample_df)
    if not match_cols:
        return pd.Series(False, index=filtered_df.index)

    work = filtered_df.copy()
    work["_row_idx"] = work.index
    keys = sample_df[match_cols].drop_duplicates()
    merged = work.merge(keys, on=match_cols, how="inner")
    sampled_idx = set(merged["_row_idx"].tolist())
    return pd.Series(filtered_df.index.isin(sampled_idx), index=filtered_df.index)
