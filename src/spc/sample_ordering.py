"""채취 표본 시계열 정렬 — 분석·표·차트 공통 순서."""
from __future__ import annotations

import pandas as pd

_TIME_LABEL_HINTS = (
    "시간", "time", "일시", "datetime", "timestamp", "날짜", "date", "transaction",
)


def resolve_sort_timestamp_series(df: pd.DataFrame) -> pd.Series:
    """정렬용 시각 열 — timestamp 우선, 없으면 measure_time·measure_date·시간형 컬럼."""
    if df is None or df.empty:
        return pd.Series(dtype="datetime64[ns]")

    for col in ("timestamp", "measure_time", "measure_date"):
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        if parsed.notna().any():
            return parsed

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().any():
                return parsed

    for col in df.columns:
        label = str(col).lower()
        if any(h in label for h in _TIME_LABEL_HINTS):
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().mean() > 0.5:
                return parsed

    return pd.Series(pd.NaT, index=df.index)


def candidate_sort_key(cand: dict) -> tuple[int, float, str]:
    """subgroup 후보 — 시간순 정렬 키 (시간 없으면 seq_start)."""
    chunk = cand.get("chunk")
    if chunk is not None and not chunk.empty:
        ts = resolve_sort_timestamp_series(chunk)
        if ts.notna().any():
            return (0, float(pd.Timestamp(ts.min()).value), "")
    seq = cand.get("seq_start")
    if seq is not None:
        return (1, float(seq), "")
    return (2, 0.0, str(cand.get("block_key", "")))


def sort_sample_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """측정 시각 기준 시계열 순 정렬.

    - subgroup_id가 있으면: 군별 최소 일시로 군 순서를 정하고, 군 내는 시간순 정렬 후
      subgroup_id를 1..N으로 재부여합니다.
    - subgroup_id 없으면: 전체 시간순 정렬.
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    out["_sort_ts"] = resolve_sort_timestamp_series(out)
    if not out["_sort_ts"].notna().any():
        out = out.drop(columns=["_sort_ts"], errors="ignore")
        if "subgroup_id" in out.columns:
            sort_cols = ["subgroup_id"]
            if "measurement_point" in out.columns:
                sort_cols.append("measurement_point")
            return out.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
        return out.reset_index(drop=True)

    if "subgroup_id" in out.columns:
        sg_first = (
            out.groupby("subgroup_id", sort=False)["_sort_ts"]
            .min()
            .sort_values(kind="mergesort")
        )
        sg_rank = {sg: i for i, sg in enumerate(sg_first.index)}
        out["_sg_rank"] = out["subgroup_id"].map(sg_rank)
        out = out.sort_values(["_sg_rank", "_sort_ts"], kind="mergesort").reset_index(drop=True)
        out["subgroup_id"] = out.groupby("_sg_rank", sort=False).ngroup() + 1
        return out.drop(columns=["_sort_ts", "_sg_rank"], errors="ignore")

    extra = ["measurement_point"] if "measurement_point" in out.columns else []
    sort_cols = ["_sort_ts", *extra]
    return (
        out.sort_values(sort_cols, kind="mergesort")
        .drop(columns=["_sort_ts"])
        .reset_index(drop=True)
    )
