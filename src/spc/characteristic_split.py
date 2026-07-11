"""검사항목·측정포인트 — 항목별 자동 분리 분석."""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from src.spc.data_extractor import (
    COLUMN_ALIASES,
    MEASUREMENT_POINT_MANUAL_MAX_LEVELS,
    MEASUREMENT_POINT_MAX_LEVELS,
    _col_key,
    _score_measurement_point_column,
)

# 우선순위: 검사항목 → 측정항목 → 측정포인트
SPLIT_COLUMNS: tuple[str, ...] = ("characteristic", "measure_item", "measurement_point")

MEASUREMENT_POINT_COLUMN = "measurement_point"
COMPOSITE_SPLIT_COLUMN = "_spc_composite_split"
COMPOSITE_SPLIT_SEP = " · "
MAX_COMPOSITE_COLUMNS = 5
MEASUREMENT_POINT_AUTO_SPLIT_MAX = 8
MEASUREMENT_POINT_MIN_ROWS_PER_LEVEL = 2


def normalize_split_value(val: object) -> str:
    """분리 키 정규화 (1.0 → '1')."""
    if val is None:
        return ""
    try:
        if isinstance(val, float) and pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "-"):
        return ""
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    return s


def is_measurement_point_split(split_column: str | None) -> bool:
    if not split_column:
        return False
    if split_column in (MEASUREMENT_POINT_COLUMN, "machine", COMPOSITE_SPLIT_COLUMN):
        return True
    key = split_column.strip().lower().replace(" ", "")
    return key in {
        "네트갯수", "값갯수", "체결부위", "측정포인트", "measurementpoint", "measurepoint", "point",
        "machine", "설비id", "설비", "설비코드", "equipment", "equipmentcode",
    }


def detect_measurement_point_column(df: pd.DataFrame) -> Optional[str]:
    """체결부위·네트 번호 등 측정 포인트 구분 열 (최고 점수 후보)."""
    if MEASUREMENT_POINT_COLUMN in df.columns:
        values = _clean_split_values(df[MEASUREMENT_POINT_COLUMN])
        if len(values) >= 2:
            return MEASUREMENT_POINT_COLUMN

    cands = list_measurement_point_column_candidates(df)
    if not cands:
        return None
    col = cands[0][0]
    if len(_clean_split_values(df[col])) >= 2:
        return col
    return None


def list_measurement_point_column_candidates(
    df: pd.DataFrame,
    *,
    for_manual: bool = False,
) -> list[tuple[str, float]]:
    """측정 포인트 구분 열 후보 (컬럼명, 점수) 내림차순."""
    max_levels = (
        MEASUREMENT_POINT_MANUAL_MAX_LEVELS if for_manual else MEASUREMENT_POINT_MAX_LEVELS
    )
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    for col in df.columns:
        score = _score_measurement_point_column(df, str(col), max_levels=max_levels)
        if score is not None:
            vals = _clean_split_values(df[col])
            if len(vals) >= 2:
                out.append((str(col), float(score)))
                seen.add(str(col))

    for col in ("characteristic", "measure_item"):
        if col not in df.columns or col in seen:
            continue
        vals = _clean_split_values(df[col])
        if len(vals) < 2:
            continue
        if for_manual and len(vals) > MEASUREMENT_POINT_MANUAL_MAX_LEVELS:
            continue
        if not for_manual and len(vals) > MEASUREMENT_POINT_MAX_LEVELS:
            continue
        out.append((col, float(len(vals)) + 5.0))
        seen.add(col)

    out.sort(key=lambda x: (-x[1], x[0]))
    return out


MANUAL_SPLIT_PRIORITY_COLUMNS: tuple[str, ...] = (
    "machine",
    "measurement_point",
    "characteristic",
    "measure_item",
    "process",
    "process_name",
    "operation",
    "operation_name",
    "line",
    "lot",
    "shift",
)


def _manual_split_column_candidates(df: pd.DataFrame) -> list[str]:
    """직접 지정용 열 후보 — 전체 열 스캔 대신 분리 가능성 있는 열만."""
    skip = _split_column_exclude_keys()
    seen: set[str] = set()
    out: list[str] = []

    for col in MANUAL_SPLIT_PRIORITY_COLUMNS:
        if col in df.columns and col not in seen:
            out.append(col)
            seen.add(col)

    scored = [c for c, _ in list_measurement_point_column_candidates(df, for_manual=True)]
    for col in scored:
        if col not in seen:
            out.append(col)
            seen.add(col)

    for col in df.columns:
        col_s = str(col)
        if col_s in seen or _col_key(col_s) in skip or col_s in skip:
            continue
        n = int(df[col_s].nunique(dropna=True))
        if 2 <= n <= MEASUREMENT_POINT_MANUAL_MAX_LEVELS:
            out.append(col_s)
            seen.add(col_s)
    return out


def build_manual_split_options(
    df: pd.DataFrame,
    *,
    column_display_names: dict[str, str] | None = None,
) -> list[dict]:
    """
    직접 지정용 — 점수·우선순위 없이 원본 데이터의 분리 가능 열·항목 전체 목록.
    """
    display = column_display_names or {}
    options: list[dict] = []
    for col_s in _manual_split_column_candidates(df):
        summary = summarize_measurement_points(df, col_s)
        if len(summary) < 2:
            continue
        options.append({
            "column": col_s,
            "display_column": display.get(col_s, col_s),
            "summary": summary,
            "point_count": len(summary),
            "point_ids": [str(s["point_id"]) for s in summary],
        })
    options.sort(key=lambda x: str(x["display_column"]))
    return options


def build_measurement_point_preview(
    df: pd.DataFrame,
    *,
    column_display_names: dict[str, str] | None = None,
) -> dict:
    """UI용 — 열 후보·포인트 목록·자동 추천 포인트."""
    display = column_display_names or {}
    cands_raw = list_measurement_point_column_candidates(df, for_manual=True)
    candidates: list[dict] = []
    seen_cols: set[str] = set()
    for col, score in cands_raw:
        seen_cols.add(col)
        summary = summarize_measurement_points(df, col)
        auto_vals = select_auto_measurement_point_values(df, col)
        candidates.append({
            "column": col,
            "display_column": display.get(col, col),
            "score": round(score, 1),
            "point_count": len(summary),
            "summary": summary,
            "auto_values": auto_vals,
            "point_ids": [str(s["point_id"]) for s in summary],
        })
    recommended = candidates[0]["column"] if candidates else None
    first = candidates[0] if candidates else {}
    return {
        "recommended_column": recommended,
        "recommended_display_column": (
            candidates[0]["display_column"] if candidates else None
        ),
        "candidates": candidates,
        "summary": first.get("summary", []),
        "auto_values": first.get("auto_values", []),
    }


def format_point_picker_option(
    point_id: str,
    split_column: str,
    *,
    row_count: int | None = None,
) -> str:
    """직접 지정 UI — 항목명 전체 표기."""
    base = format_split_label(point_id, split_column)
    if row_count is not None:
        return f"{base} · n={row_count}"
    return base


def point_picker_option_map(summary: list[dict], split_column: str) -> dict[str, str]:
    """표시 라벨 → point_id (multiselect용, 라벨은 항목명 전체)."""
    out: dict[str, str] = {}
    used: set[str] = set()
    for item in summary:
        pid = str(item["point_id"])
        label = format_point_picker_option(pid, split_column, row_count=item.get("row_count"))
        key = label
        n = 2
        while key in used:
            key = f"{label} [{pid}]" if n == 2 else f"{label} [{pid}] #{n}"
            n += 1
        used.add(key)
        out[key] = pid
    return out


def detect_split_column(df: pd.DataFrame) -> Optional[str]:
    """복수 항목/포인트가 있는 표준 컬럼명 반환 (없으면 None)."""
    for col in ("characteristic", "measure_item"):
        if col not in df.columns:
            continue
        values = _clean_split_values(df[col])
        if len(values) >= 2:
            return col
    return detect_measurement_point_column(df)


def list_split_values(df: pd.DataFrame, column: str) -> list[str]:
    """항목·포인트 값 목록 (정렬)."""
    values = _clean_split_values(df[column])
    return sorted(values, key=_natural_sort_key)


def select_auto_measurement_point_values(
    df: pd.DataFrame,
    column: str,
    *,
    max_points: int = MEASUREMENT_POINT_AUTO_SPLIT_MAX,
    min_rows_per_level: int = MEASUREMENT_POINT_MIN_ROWS_PER_LEVEL,
) -> list[str]:
    """
    자동 분석 대상 측정 포인트 선정.
    - 포인트당 최소 행 수 미달 제외
    - max_points 초과 시 데이터량 상위만 선택
    """
    summary = summarize_measurement_points(df, column)
    viable = [s for s in summary if s["row_count"] >= min_rows_per_level]
    if not viable:
        return []
    if len(viable) <= max_points:
        return [str(s["point_id"]) for s in viable]
    viable.sort(key=lambda s: (-s["row_count"], _natural_sort_key(str(s["point_id"]))))
    return [str(s["point_id"]) for s in viable[:max_points]]


def build_composite_split_key(row: pd.Series, columns: list[str]) -> str:
    """2~5개 열 값을 하나의 분리 키로 (예: 'EQ-01 · 품번A · 1')."""
    cols = [c for c in columns if c][:MAX_COMPOSITE_COLUMNS]
    parts: list[str] = []
    for col in cols:
        parts.append(normalize_split_value(row[col]) if col in row.index else "")
    if len(parts) < 2 or any(not p for p in parts):
        return ""
    return COMPOSITE_SPLIT_SEP.join(parts)


def apply_composite_split_column(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """복합 분리 열 추가 (2~5열)."""
    cols = [c for c in columns if c][:MAX_COMPOSITE_COLUMNS]
    if len(cols) < 2:
        return df
    out = df.copy()
    out[COMPOSITE_SPLIT_COLUMN] = out.apply(
        lambda r: build_composite_split_key(r, cols),
        axis=1,
    )
    return out


def recommend_composite_column_pair(options: list[dict]) -> tuple[str, str] | None:
    """UI 추천 — 설비+품목 등 2열 조합."""
    triple = recommend_composite_columns(options, n_columns=2)
    if triple and len(triple) >= 2:
        return triple[0], triple[1]
    return None


_COMPOSITE_PAIR_PRIORITY: tuple[tuple[str, str], ...] = (
    ("characteristic", "item"),
    ("item", "characteristic"),
    ("measure_item", "item"),
    ("item", "machine"),
    ("machine", "item"),
    ("characteristic", "machine"),
    ("machine", "characteristic"),
    ("measure_item", "machine"),
    ("item", "measurement_point"),
)

_COMPOSITE_TRIPLE_PRIORITY: tuple[tuple[str, str, str], ...] = (
    ("machine", "item", "measurement_point"),
    ("machine", "item", "shift"),
    ("machine", "characteristic", "measurement_point"),
    ("item", "machine", "measurement_point"),
    ("machine", "process", "measurement_point"),
)

_COMPOSITE_EXTRA_PRIORITY: tuple[str, ...] = (
    "shift",
    "lot",
    "process",
    "equipment_id",
    "date",
    "operator",
    "characteristic",
    "measure_item",
)


def _recommend_composite_triple(cols: set[str], pair: tuple[str, str]) -> list[str] | None:
    for a, b, c in _COMPOSITE_TRIPLE_PRIORITY:
        if a in cols and b in cols and c in cols:
            return [a, b, c]
    for c in sorted(cols - set(pair)):
        return [pair[0], pair[1], c]
    return None


def _extend_composite_columns(base: list[str], cols: set[str], n_columns: int) -> list[str] | None:
    if len(base) >= n_columns:
        return base[:n_columns]
    remaining = list(cols - set(base))
    extra: list[str] = []
    for pref in _COMPOSITE_EXTRA_PRIORITY:
        if pref in remaining and pref not in extra:
            extra.append(pref)
    for col in sorted(remaining):
        if col not in extra:
            extra.append(col)
    need = n_columns - len(base)
    if len(extra) < need:
        return None
    return base + extra[:need]


def recommend_composite_columns(
    options: list[dict],
    *,
    n_columns: int = 2,
) -> list[str] | None:
    """UI 추천 — 2~5열 복합 분리 조합."""
    n_columns = max(2, min(n_columns, MAX_COMPOSITE_COLUMNS))
    cols = {str(o["column"]) for o in options}
    if len(cols) < n_columns:
        return None

    pair: tuple[str, str] | None = None
    for a, b in _COMPOSITE_PAIR_PRIORITY:
        if a in cols and b in cols:
            pair = (a, b)
            break
    if not pair:
        names = [str(o["column"]) for o in options]
        if len(names) >= 2:
            pair = (names[0], names[1])
        else:
            return None

    if n_columns == 2:
        return [pair[0], pair[1]]

    triple = _recommend_composite_triple(cols, pair)
    if not triple:
        return None
    return _extend_composite_columns(triple, cols, n_columns)


def summarize_composite_split(
    df: pd.DataFrame,
    columns: list[str],
    *,
    display_names: dict[str, str] | None = None,
) -> list[dict]:
    """2~5열 복합 분리 — 조합별 행 수 요약."""
    cols = [c for c in columns if c][:MAX_COMPOSITE_COLUMNS]
    if len(cols) < 2:
        return []
    display = display_names or {}
    work = apply_composite_split_column(df, cols)
    summary = summarize_measurement_points(work, COMPOSITE_SPLIT_COLUMN)
    labels = [display.get(c, c) for c in cols]
    composite_display = COMPOSITE_SPLIT_SEP.join(labels)
    for item in summary:
        item["label"] = str(item["point_id"])
        item["composite_columns"] = list(cols)
        item["composite_display"] = composite_display
    return summary


def resolve_split_plan(
    filtered: pd.DataFrame,
    *,
    filter_characteristic: str | None = None,
    auto_split_characteristics: bool = True,
    measurement_point_mode: str = "auto",
    measurement_point_column: str | None = None,
    measurement_point_columns: list[str] | None = None,
    measurement_point_values: list[str] | None = None,
    max_auto_measurement_points: int = MEASUREMENT_POINT_AUTO_SPLIT_MAX,
) -> tuple[pd.DataFrame, str | None, list[str]]:
    """
    항목·측정 포인트별 분리 분석 계획.
    Returns (working_df, split_column, split_values). 빈 values → 단일 분석.
    """
    working = filtered.copy()
    mcols = [c for c in (measurement_point_columns or []) if c]

    if filter_characteristic:
        return working, None, []

    if measurement_point_mode == "none":
        if auto_split_characteristics:
            col = detect_split_column(working)
            if col and not is_measurement_point_split(col):
                vals = list_split_values(working, col)
                if len(vals) >= 2:
                    return working, col, vals
        return working, None, []

    if len(mcols) >= 2:
        use_cols = mcols[:MAX_COMPOSITE_COLUMNS]
        for c in use_cols:
            if c not in working.columns:
                return working, None, []
        working = apply_composite_split_column(working, use_cols)
        col = COMPOSITE_SPLIT_COLUMN
    else:
        col = measurement_point_column
        if not col or col not in working.columns:
            col = detect_measurement_point_column(working)
        if not col:
            return working, None, []

    available = list_split_values(working, col)

    if measurement_point_mode == "manual":
        picked = list(measurement_point_values or [])
        if not picked:
            return working, None, []
        norm_avail = {normalize_split_value(v) for v in available}
        vals = [v for v in picked if normalize_split_value(v) in norm_avail]
        return working, col, vals

    if len(available) < 2:
        return working, col, available

    selected = select_auto_measurement_point_values(
        working, col, max_points=max_auto_measurement_points,
    )
    return working, col, selected


def summarize_measurement_points(df: pd.DataFrame, column: str | None = None) -> list[dict]:
    """UI용 측정 포인트별 행 수 요약 (groupby — 대용량 데이터 대응)."""
    col = column or detect_measurement_point_column(df)
    if not col or col not in df.columns:
        return []

    keys = df[col].map(normalize_split_value)
    valid = keys != ""
    if not valid.any():
        return []

    work = pd.DataFrame({"_key": keys[valid]}, index=df.index[valid])
    counts = work.groupby("_key", sort=False).size()

    ts_bounds: dict[str, tuple[str | None, str | None]] = {}
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df.loc[valid, "timestamp"], errors="coerce")
        ts_frame = pd.DataFrame({"_key": keys[valid], "ts": ts.values})
        ts_frame = ts_frame.dropna(subset=["ts"])
        if not ts_frame.empty:
            agg = ts_frame.groupby("_key")["ts"].agg(["min", "max"])
            for key, row in agg.iterrows():
                ts_bounds[str(key)] = (
                    row["min"].strftime("%Y-%m-%d %H:%M"),
                    row["max"].strftime("%Y-%m-%d %H:%M"),
                )

    rows: list[dict] = []
    for idx in sorted(counts.index, key=lambda x: _natural_sort_key(str(x))):
        val = str(idx)
        ts_min, ts_max = ts_bounds.get(val, (None, None))
        rows.append(
            {
                "point_id": val,
                "label": format_split_label(val, col),
                "row_count": int(counts.loc[idx]),
                "period_start": ts_min,
                "period_end": ts_max,
            }
        )
    return rows


def _split_column_exclude_keys() -> set[str]:
    """직접 지정 열 목록에서 제외할 표준 컬럼 (측정값·공차·시간 등)."""
    keys: set[str] = set()
    for group in ("value", "timestamp", "measure_date", "measure_time", "usl", "lsl", "target", "source"):
        keys.update(_col_key(a) for a in COLUMN_ALIASES.get(group, []))
    keys.update({
        "value", "timestamp", "measuredate", "measuretime",
        "usl", "lsl", "target", "source",
    })
    return keys


def format_split_label(value: str, split_column: str) -> str:
    """분리 키 → 사용자 표시 라벨."""
    display = normalize_split_value(value) or str(value)
    if split_column == COMPOSITE_SPLIT_COLUMN:
        return display
    if split_column == "machine":
        return f"설비 {display}"
    if is_measurement_point_split(split_column):
        return f"측정 포인트 {display}"
    if split_column in ("characteristic", "measure_item"):
        return display
    return display


def _clean_split_values(series: pd.Series) -> list[str]:
    vals = series.dropna()
    out: set[str] = set()
    for v in vals:
        key = normalize_split_value(v)
        if key:
            out.add(key)
    return sorted(out, key=_natural_sort_key)


def _natural_sort_key(text: str) -> tuple:
    parts = re.split(r"(\d+)", str(text))
    key: list = []
    for p in parts:
        if p.isdigit():
            key.append(int(p))
        else:
            key.append(p.lower())
    return tuple(key)


def safe_filename_slug(text: str, max_len: int = 48) -> str:
    """보고서 파일명용."""
    s = re.sub(r'[<>:"/\\|?*]', "_", str(text).strip())
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return "item"
    return s[:max_len]
