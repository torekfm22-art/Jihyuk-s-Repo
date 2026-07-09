"""동일 공정 조건 내 연속 subgroup 재구성."""
from __future__ import annotations

from typing import Literal

import pandas as pd

from src.spc.sample_ordering import sort_sample_dataframe

IncompletePolicy = Literal["exclude", "keep_with_warning", "merge_not_allowed"]

BOUNDARY_COLUMN_CANDIDATES = (
    "_strat_date",
    "shift",
    "lot",
    "measure_date",
    "timestamp",
    "measurement_point",
    "machine",
    "line",
    "operator",
)


def _boundary_key(row: pd.Series, cols: list[str]) -> tuple:
    parts: list[str] = []
    for col in cols:
        if col not in row.index:
            parts.append("")
            continue
        val = row[col]
        if pd.isna(val):
            parts.append("")
        elif col in ("timestamp", "_sort_ts"):
            ts = pd.Timestamp(val)
            parts.append(ts.strftime("%Y-%m-%d") if pd.notna(ts) else "")
        else:
            parts.append(str(val).strip())
    return tuple(parts)


def _boundary_cardinality(grp: pd.DataFrame, col: str) -> int:
    if col not in grp.columns:
        return 0
    if col in ("timestamp", "_sort_ts"):
        ts = pd.to_datetime(grp[col], errors="coerce")
        return int(ts.dt.strftime("%Y-%m-%d").nunique(dropna=False))
    return int(grp[col].nunique(dropna=False))


def _resolve_boundary_candidates(df: pd.DataFrame, split_columns: list[str]) -> list[str]:
    """분리 기준 열을 제외한 경계 후보 (split_columns는 이미 group 내 상수)."""
    cols: list[str] = []
    for c in BOUNDARY_COLUMN_CANDIDATES:
        if c in df.columns and c not in split_columns and c not in cols:
            cols.append(c)
    if "_strat_date" in df.columns and "_strat_date" not in cols:
        cols.append("_strat_date")
    if "timestamp" in df.columns and "timestamp" not in cols and "_strat_date" not in cols:
        cols.append("timestamp")
    return cols


def _effective_boundary_columns(
    grp: pd.DataFrame,
    split_columns: list[str],
    candidate_cols: list[str],
    subgroup_size: int,
) -> list[str]:
    """그룹 내에서 실질적 경계가 되는 열만 선택 (과도한 분할 방지)."""
    n = len(grp)
    if n < subgroup_size:
        return []
    max_segments = max(1, n // subgroup_size)
    effective: list[str] = []
    for col in candidate_cols:
        if col in split_columns or col.startswith("_sort"):
            continue
        if col not in grp.columns:
            continue
        nuniq = _boundary_cardinality(grp, col)
        if nuniq < 2:
            continue
        if nuniq > max_segments:
            continue
        effective.append(col)
    return effective


def _build_subgroups(
    work: pd.DataFrame,
    split_columns: list[str],
    *,
    subgroup_size: int,
    boundary_cols: list[str] | None,
    incomplete_policy: IncompletePolicy,
) -> tuple[list[pd.DataFrame], list[str]]:
    warnings: list[str] = []
    out_rows: list[pd.DataFrame] = []
    global_sg = 1
    candidate_cols = _resolve_boundary_candidates(work, split_columns)

    def gkey_label(gkey) -> str:
        return "|".join(str(x) for x in (gkey if isinstance(gkey, tuple) else (gkey,)))

    def emit_subgroup(rows: list[pd.Series], gkey, reason: str) -> None:
        nonlocal global_sg
        if not rows:
            return
        if len(rows) < subgroup_size:
            if incomplete_policy == "exclude":
                warnings.append(
                    f"그룹 {gkey_label(gkey)}: {reason} — {len(rows)}건(< n={subgroup_size}) 제외"
                )
                return
            warnings.append(
                f"그룹 {gkey_label(gkey)}: {reason} — {len(rows)}건(< n={subgroup_size}) 경고 포함"
            )
        block = pd.DataFrame(rows)
        block["subgroup_id"] = global_sg
        block["split_key"] = gkey_label(gkey)
        block["sampling_strategy"] = "stratified_reconstruct"
        out_rows.append(block)
        global_sg += 1

    for gkey, grp in work.groupby(split_columns, dropna=False, sort=False):
        grp = grp.sort_values(["_sort_ts"], kind="mergesort", na_position="last")
        active_boundaries = (
            boundary_cols
            if boundary_cols is not None
            else _effective_boundary_columns(grp, split_columns, candidate_cols, subgroup_size)
        )

        buffer: list[pd.Series] = []
        prev: pd.Series | None = None

        for _, row in grp.iterrows():
            if prev is not None and buffer and active_boundaries:
                boundary_hit = _boundary_key(prev, active_boundaries) != _boundary_key(row, active_boundaries)
                if boundary_hit:
                    emit_subgroup(buffer, gkey, "경계 변경")
                    buffer = []
                elif len(buffer) >= subgroup_size:
                    emit_subgroup(buffer[:subgroup_size], gkey, f"n={subgroup_size} 충족")
                    buffer = buffer[subgroup_size:]
            elif prev is not None and buffer and not active_boundaries and len(buffer) >= subgroup_size:
                emit_subgroup(buffer[:subgroup_size], gkey, f"n={subgroup_size} 충족")
                buffer = buffer[subgroup_size:]
            buffer.append(row)
            prev = row

        while len(buffer) >= subgroup_size:
            emit_subgroup(buffer[:subgroup_size], gkey, f"n={subgroup_size} 충족")
            buffer = buffer[subgroup_size:]
        if buffer:
            emit_subgroup(buffer, gkey, "그룹 종료")

    return out_rows, warnings


def reconstruct_stratified_subgroups(
    df: pd.DataFrame,
    split_columns: list[str],
    *,
    subgroup_size: int = 5,
    value_col: str = "value",
    incomplete_policy: IncompletePolicy = "exclude",
    min_subgroup_count: int = 25,
) -> tuple[pd.DataFrame, list[str]]:
    """split_columns 기준 group_key별로 시간순 연속 n개 subgroup 구성."""
    if df is None or df.empty:
        raise ValueError("재구성할 데이터가 없습니다.")
    if not split_columns:
        raise ValueError("split_columns를 1개 이상 지정하세요.")
    for col in split_columns:
        if col not in df.columns:
            raise ValueError(f"분리 기준 열 '{col}'이 데이터에 없습니다.")
        from src.spc.mixed_distribution_stratification import is_valid_stratification_split_column

        if not is_valid_stratification_split_column(df, col, value_col=value_col, require_variation=False):
            raise ValueError(
                f"분리 기준 '{col}'은(는) 공정·조건 열이 아닙니다. "
                "교대·LOT·날짜·설비·측정호기 등 범주형 조건만 사용할 수 있습니다. "
                "다른 측정치(무게·도포량 등)로는 분리할 수 없습니다."
            )

    work = df.dropna(subset=[value_col]).copy()
    if work.empty:
        raise ValueError("유효한 측정값이 없습니다.")

    if "timestamp" in work.columns:
        work["_sort_ts"] = pd.to_datetime(work["timestamp"], errors="coerce")
    else:
        from src.spc.sample_ordering import resolve_sort_timestamp_series

        work["_sort_ts"] = resolve_sort_timestamp_series(work)

    warnings: list[str] = []
    out_rows: list[pd.DataFrame] = []

    strategies: list[tuple[str, IncompletePolicy, list[str] | None]] = [
        ("경계 열 기반", incomplete_policy, None),
    ]
    if incomplete_policy == "exclude":
        strategies.append(("미완성 subgroup 포함", "keep_with_warning", None))
    strategies.append(("시간순 연속 묶음(경계 무시)", "keep_with_warning", []))

    for label, policy, boundaries in strategies:
        out_rows, attempt_warnings = _build_subgroups(
            work,
            split_columns,
            subgroup_size=subgroup_size,
            boundary_cols=boundaries,
            incomplete_policy=policy,
        )
        if out_rows:
            if label != "경계 열 기반":
                warnings.append(f"subgroup 재구성: {label} 방식으로 대체 적용")
            warnings.extend(attempt_warnings)
            break
        warnings.extend(attempt_warnings)

    if not out_rows:
        raise ValueError(
            "유효한 subgroup을 구성하지 못했습니다. "
            f"조건별 연속 데이터가 n={subgroup_size}개 미만이거나 분리 기준 그룹이 너무 작습니다. "
            "subgroup 크기를 줄이거나 미완성 subgroup 포함 정책을 사용하세요."
        )

    result = pd.concat(out_rows, ignore_index=True)
    result = sort_sample_dataframe(result.drop(columns=["_sort_ts"], errors="ignore"))
    n_sg = int(result["subgroup_id"].nunique())
    if n_sg < min_subgroup_count:
        warnings.append(
            f"subgroup 수 {n_sg} < 최소 {min_subgroup_count} — 관리도·공정능력 해석 제한"
        )

    mixed = _detect_mixed_keys_in_subgroups(result, split_columns)
    if mixed:
        warnings.append(f"subgroup 내부 혼합 감지: {mixed}")

    return result, warnings


def _detect_mixed_keys_in_subgroups(df: pd.DataFrame, split_columns: list[str]) -> str | None:
    if "subgroup_id" not in df.columns:
        return None
    for col in split_columns:
        if col not in df.columns:
            continue
        counts = df.groupby("subgroup_id")[col].nunique(dropna=False)
        bad = counts[counts > 1]
        if not bad.empty:
            return f"{col} (subgroup {bad.index[0]})"
    return None
