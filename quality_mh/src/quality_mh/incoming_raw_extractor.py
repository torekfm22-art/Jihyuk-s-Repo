"""입고검사 Raw data 추출 및 집계.

원본: 검사빈도(부품별) 리스트_24/25년, 생산계획 연동
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from quality_mh.constants import INSPECTION_TYPES
from quality_mh.incoming_frequency_analyzer import (
    INCOMING_TYPES,
    YearPivotInput,
    YearQuantityInput,
    _trim_partial_tail_month,
)

TYPE_ALIASES = {
    "샘플링": "샘플링",
    "전수": "전수",
    "무검사": "무검사",
    "무 검사": "무검사",
}


@dataclass
class RawExtractionResult:
    year: int
    records: pd.DataFrame = field(default_factory=pd.DataFrame)
    pivot: YearPivotInput = field(default_factory=lambda: YearPivotInput(year=0))
    quantities: YearQuantityInput = field(default_factory=lambda: YearQuantityInput(year=0))
    audit: list[str] = field(default_factory=list)


def _normalize_col_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name).strip())


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {_normalize_col_name(c): c for c in columns}
    for cand in candidates:
        key = _normalize_col_name(cand)
        if key in normalized:
            return normalized[key]
    for col in columns:
        ncol = _normalize_col_name(col)
        for cand in candidates:
            if _normalize_col_name(cand) in ncol:
                return col
    return None


def _normalize_inspection_type(value: object) -> str | None:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return TYPE_ALIASES.get(text, text if text in INSPECTION_TYPES else None)


def _coerce_inspection_list_headers(df: pd.DataFrame) -> pd.DataFrame:
    """header=None으로 읽힌 시트면 헤더 행 자동 탐지."""
    cols = [str(c) for c in df.columns]
    if any("검사레벨" in c or "수량" in c for c in cols):
        return df

    preview = df.head(10)
    header_idx = 0
    for i in range(len(preview)):
        row_text = " ".join(str(v) for v in preview.iloc[i].tolist())
        if "검사레벨" in row_text and "수량" in row_text:
            header_idx = i
            break
    header = df.iloc[header_idx].tolist()
    body = df.iloc[header_idx + 1 :].copy()
    clean_header: list[str] = []
    seen: dict[str, int] = {}
    for idx, name in enumerate(header):
        text = str(name).strip() if pd.notna(name) else f"col_{idx}"
        if text in seen:
            seen[text] += 1
            text = f"{text}_{seen[text]}"
        else:
            seen[text] = 0
        clean_header.append(text)
    body.columns = clean_header
    return body.reset_index(drop=True)


def parse_inspection_list_raw(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """검사빈도(부품별) 리스트 시트 → 정규화 long format."""
    if df.empty:
        return pd.DataFrame()

    work = _coerce_inspection_list_headers(df.copy())
    type_col = _find_column(
        list(work.columns),
        ["양산입고\n검사레벨", "양산입고검사레벨", "검사레벨", "검사유형"],
    )
    qty_col = _find_column(list(work.columns), ["수량"])
    year_col = _find_column(list(work.columns), ["년", "연"])
    month_col = _find_column(list(work.columns), ["월"])
    part_col = _find_column(list(work.columns), ["품번"])
    vendor_col = _find_column(list(work.columns), ["거래처(공급사)", "거래처"])
    status_col = _find_column(list(work.columns), ["검사현황", "입고\n현황"])

    required = [type_col, qty_col, year_col, month_col]
    if any(c is None for c in required):
        missing = [
            name
            for name, col in zip(
                ["검사레벨", "수량", "년", "월"],
                required,
            )
            if col is None
        ]
        raise ValueError(f"검사빈도 리스트 필수 컬럼 누락: {missing}")

    def _series(col: str | None, default: object = "") -> pd.Series:
        if col is None:
            return pd.Series([default] * len(work))
        data = work[col]
        if isinstance(data, pd.DataFrame):
            data = data.iloc[:, 0]
        return data

    rows = pd.DataFrame(
        {
            "year": pd.to_numeric(_series(year_col), errors="coerce"),
            "month": pd.to_numeric(_series(month_col), errors="coerce"),
            "inspection_type": _series(type_col).map(_normalize_inspection_type),
            "quantity": pd.to_numeric(_series(qty_col), errors="coerce").fillna(0),
            "part_no": _series(part_col),
            "vendor": _series(vendor_col),
            "inspection_status": _series(status_col),
        }
    )
    rows = rows[rows["year"] == year]
    rows = rows[rows["inspection_type"].notna()]
    rows = rows[rows["month"].between(1, 12)]
    rows["source_year"] = year
    return rows.reset_index(drop=True)


def aggregate_inspection_counts(raw_df: pd.DataFrame, year: int) -> YearPivotInput:
    """Raw → 월별 검사건수 pivot."""
    result = YearPivotInput(year=year)
    if raw_df.empty:
        return result

    counts = (
        raw_df.groupby(["inspection_type", "month"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=list(INCOMING_TYPES), fill_value=0)
    )
    for t in INCOMING_TYPES:
        if t in counts.index:
            for month in range(1, 13):
                val = counts.loc[t, month] if month in counts.columns else 0
                result.counts[t][month - 1] = float(val) if val else 0.0
        else:
            result.counts[t] = [0.0] * 12

    filled_months = max(
        (m for m in range(12, 0, -1) if any(result.counts[t][m - 1] for t in INCOMING_TYPES)),
        default=0,
    )
    result.actual_months = _trim_partial_tail_month(result.counts) or filled_months
    if result.actual_months < filled_months:
        for t in INCOMING_TYPES:
            for idx in range(result.actual_months, 12):
                result.counts[t][idx] = None
    return result


def aggregate_inbound_quantity(raw_df: pd.DataFrame, year: int) -> list[float | None]:
    """Raw 수량 합계 → 월별 입고수량(부품)."""
    if raw_df.empty:
        return [None] * 12
    qty = raw_df.groupby("month")["quantity"].sum()
    return [float(qty.get(m, 0.0)) if m in qty.index else 0.0 for m in range(1, 13)]


def parse_cheonan_production_plan(df: pd.DataFrame, year: int) -> list[float | None]:
    """생산계획 연동 → 천안EBS 합계 행 월별 생산수량."""
    if df.empty:
        return [None] * 12

    raw = df.fillna("")
    month_cols: list[int] = []
    header_row = -1
    for ridx, row in raw.iterrows():
        hits = 0
        cols: list[tuple[int, int]] = []
        for cidx, val in enumerate(row.tolist()):
            text = str(val).strip()
            if text.endswith("월") and text[:-1].isdigit():
                month = int(text[:-1])
                cols.append((month, cidx))
                hits += 1
        if hits >= 6:
            cols.sort(key=lambda x: x[0])
            ordered = [None] * 12
            for month, cidx in cols:
                if 1 <= month <= 12:
                    ordered[month - 1] = cidx
            month_cols = ordered
            header_row = int(ridx)
            break

    if not any(c is not None for c in month_cols):
        return [None] * 12

    for ridx, row in raw.iterrows():
        if int(ridx) <= header_row:
            continue
        label = str(row.iloc[1]).strip() if len(row) > 1 else ""
        if label != "합계":
            continue
        # 천안EBS 블록 합계 (첫 번째 합계 행)
        values: list[float | None] = [None] * 12
        for month_idx, col_idx in enumerate(month_cols):
            if col_idx is None or col_idx >= len(row):
                continue
            try:
                values[month_idx] = float(row.iloc[col_idx])
            except (TypeError, ValueError):
                continue
        if any(v is not None for v in values):
            return values

    return [None] * 12


def extract_incoming_raw(
    inspection_list_df: pd.DataFrame,
    year: int,
    production_plan_df: pd.DataFrame | None = None,
) -> RawExtractionResult:
    """단일 연도 Raw 추출 + 1차 집계."""
    records = parse_inspection_list_raw(inspection_list_df, year)
    pivot = aggregate_inspection_counts(records, year)
    quantities = YearQuantityInput(
        year=year,
        inbound_qty=aggregate_inbound_quantity(records, year),
    )
    if production_plan_df is not None:
        quantities.production_qty = parse_cheonan_production_plan(production_plan_df, year)

    audit = [
        f"{year}년 Raw {len(records):,}건 추출",
        f"{year}년 검사건수 pivot 생성 (실적 {pivot.actual_months}개월)",
        f"{year}년 입고수량 = Raw 수량 월별 합계",
    ]
    if any(v is not None for v in quantities.production_qty):
        audit.append(f"{year}년 생산수량 = 생산계획 연동(천안EBS 합계)")

    return RawExtractionResult(
        year=year,
        records=records,
        pivot=pivot,
        quantities=quantities,
        audit=audit,
    )


def pivot_to_dataframe(pivot: YearPivotInput) -> pd.DataFrame:
    """검사건수 pivot → 표 형태."""
    rows = []
    for t in INCOMING_TYPES + ("합계",):
        values = []
        for m in range(12):
            if t == "합계":
                vals = [pivot.counts.get(x, [None] * 12)[m] for x in INCOMING_TYPES]
                num = sum(v for v in vals if v is not None)
                values.append(num if num else None)
            else:
                values.append(pivot.counts.get(t, [None] * 12)[m])
        rows.append(
            {
                "year": pivot.year,
                "inspection_type": t,
                **{f"m{m:02d}": values[m - 1] for m in range(1, 13)},
                "annual_total": sum(v for v in values if v is not None),
            }
        )
    return pd.DataFrame(rows)


def find_inspection_list_sheet(sheets: dict[str, pd.DataFrame], year: int) -> pd.DataFrame | None:
    yy = str(year)[2:]
    for name, frame in sheets.items():
        if "리스트" not in name:
            continue
        if f"리스트_{yy}" in name or f"_{yy}년" in name:
            return frame
    return None
