"""앵커(Y) 시각 기준 시간 창 매칭 및 wide 테이블 생성."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

from quality_xy.graph_linker import DatasetGraph, LinkStep
from quality_xy.loader import DatasetProfile, normalize_key_value, parse_datetime_series


MatchStrategy = Literal["nearest", "mean", "first", "last", "count"]


@dataclass
class XFactorSpec:
    dataset: str
    column: str
    alias: str | None = None
    strategy: MatchStrategy = "nearest"

    @property
    def output_name(self) -> str:
        return self.alias or f"{self.dataset}__{self.column}"


@dataclass
class MatchConfig:
    anchor_dataset: str
    anchor_time_col: str
    y_column: str
    window_minutes: int = 60
    x_factors: list[XFactorSpec] = field(default_factory=list)


def _resolve_target_key(
    profiles: dict[str, DatasetProfile],
    anchor_row: pd.Series,
    path: list[LinkStep],
) -> tuple[str, str] | None:
    """연결 경로를 따라 대상 데이터셋 조회용 (컬럼, 키값)을 반환."""
    if not path:
        return None

    carry_value: str | None = None
    for i, step in enumerate(path):
        if i == 0:
            carry_value = normalize_key_value(anchor_row.get(step.from_column))
        else:
            prev = path[i - 1]
            mid_df = profiles[step.from_dataset].df
            link_col = prev.to_column
            matched = mid_df[mid_df[link_col].map(normalize_key_value) == carry_value]
            if matched.empty:
                return None
            carry_value = normalize_key_value(matched.iloc[0][step.from_column])

        if carry_value is None:
            return None
        if i == len(path) - 1:
            return step.to_column, carry_value

    return None


def _rows_for_keys(
    df: pd.DataFrame,
    key_col: str,
    key_value: str,
    time_series: pd.Series,
    anchor_time: pd.Timestamp,
    window: pd.Timedelta,
) -> pd.DataFrame:
    mask = df[key_col].map(normalize_key_value) == key_value
    subset = df.loc[mask].copy()
    if subset.empty:
        return subset
    subset["_parsed_time"] = time_series.loc[subset.index]
    subset = subset[subset["_parsed_time"].notna()]
    if subset.empty:
        return subset
    delta = (subset["_parsed_time"] - anchor_time).abs()
    subset = subset.loc[delta <= window]
    return subset


def _aggregate_match(
    values: pd.Series,
    strategy: MatchStrategy,
    anchor_time: pd.Timestamp,
    times: pd.Series,
) -> Any:
    numeric = pd.to_numeric(values, errors="coerce")
    if strategy == "count":
        return int(len(values))
    if strategy == "first":
        return values.iloc[0] if len(values) else None
    if strategy == "last":
        return values.iloc[-1] if len(values) else None
    if strategy == "mean" and numeric.notna().any():
        return float(numeric.mean())
    if strategy == "nearest" and len(values):
        idx = (times - anchor_time).abs().idxmin()
        return values.loc[idx]
    return values.iloc[0] if len(values) else None


def build_wide_table(
    profiles: dict[str, DatasetProfile],
    graph: DatasetGraph,
    config: MatchConfig,
    *,
    anchor_key_col: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    앵커 데이터셋 각 행을 기준으로 X 인자를 같은 시간 창 안에서 매칭해 wide 테이블 생성.

    Returns:
        wide_df: 분석용 (Y + X1, X2, ...)
        detail_df: 매칭 성공/실패 및 사용 키 기록
    """
    anchor_name = config.anchor_dataset
    anchor_prof = profiles[anchor_name]
    anchor_df = anchor_prof.df
    anchor_times = parse_datetime_series(anchor_df, config.anchor_time_col)

    key_col = anchor_key_col or (anchor_prof.suggested_keys[0] if anchor_prof.suggested_keys else None)

    wide_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []

    window = pd.Timedelta(minutes=config.window_minutes)

    for idx, row in anchor_df.iterrows():
        anchor_time = anchor_times.loc[idx]
        if pd.isna(anchor_time):
            detail_rows.append({"anchor_index": idx, "status": "no_anchor_time"})
            continue

        out: dict[str, Any] = {
            "_anchor_index": idx,
            "_anchor_time": anchor_time,
            config.y_column: row.get(config.y_column),
        }
        detail: dict[str, Any] = {
            "anchor_index": idx,
            "anchor_time": anchor_time,
            "status": "ok",
        }

        anchor_keys: dict[str, str] = {}
        if key_col and key_col in row.index:
            nk = normalize_key_value(row[key_col])
            if nk:
                anchor_keys[key_col] = nk
                detail["anchor_key"] = f"{key_col}={nk}"

        for spec in config.x_factors:
            target = spec.dataset
            path = graph.path_from_anchor(anchor_name, target)
            if path is None and target != anchor_name:
                out[spec.output_name] = None
                detail[f"{spec.output_name}_status"] = "no_path"
                continue

            prof = profiles[target]
            target_df = prof.df
            time_col = prof.datetime_col
            if not time_col:
                out[spec.output_name] = None
                detail[f"{spec.output_name}_status"] = "no_time_col"
                continue

            target_times = parse_datetime_series(target_df, time_col)

            if target == anchor_name:
                lookup_col = spec.column
                key_value = normalize_key_value(row.get(lookup_col))
                if key_value is None:
                    subset = target_df.loc[[idx]] if idx in target_df.index else pd.DataFrame()
                else:
                    subset = _rows_for_keys(target_df, lookup_col, key_value, target_times, anchor_time, window)
            else:
                if not path:
                    out[spec.output_name] = None
                    detail[f"{spec.output_name}_status"] = "no_path"
                    continue
                resolved = _resolve_target_key(profiles, row, path)
                if not resolved:
                    out[spec.output_name] = None
                    detail[f"{spec.output_name}_status"] = "no_key"
                    continue
                lookup_col, key_value = resolved
                if not key_value:
                    out[spec.output_name] = None
                    detail[f"{spec.output_name}_status"] = "no_key"
                    continue
                subset = _rows_for_keys(target_df, lookup_col, key_value, target_times, anchor_time, window)

            if subset.empty:
                out[spec.output_name] = None
                detail[f"{spec.output_name}_status"] = "no_match"
                continue

            val = _aggregate_match(
                subset[spec.column],
                spec.strategy,
                anchor_time,
                subset["_parsed_time"],
            )
            out[spec.output_name] = val
            detail[f"{spec.output_name}_status"] = f"matched_{len(subset)}"
            detail[f"{spec.output_name}_match_count"] = len(subset)

        wide_rows.append(out)
        detail_rows.append(detail)

    wide_df = pd.DataFrame(wide_rows)
    detail_df = pd.DataFrame(detail_rows)
    return wide_df, detail_df
