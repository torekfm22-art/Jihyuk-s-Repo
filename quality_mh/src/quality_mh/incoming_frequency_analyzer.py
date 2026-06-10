"""입고검사 발생빈도 분석(생산계획 연동) 자동 집계 엔진.

천안EBS 입고 MH 근거_v2 시트 로직을 코드화:
- 입고검사 건수 (샘플링/전수/무검사/합계)
- 입고수량(부품), 생산수량(완제품)
- 생산수량/입고수량, 입고검사/부품수량
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quality_mh.constants import INSPECTION_TYPES

INCOMING_TYPES = ("샘플링", "전수", "무검사")
MONTHS = list(range(1, 13))
MONTH_COLS = [f"m{m:02d}" for m in MONTHS]


@dataclass
class YearPivotInput:
    """Pivot 시트에서 추출한 월별 검사건수."""

    year: int
    counts: dict[str, list[float | None]] = field(default_factory=dict)
    actual_months: int = 12

    def __post_init__(self) -> None:
        for t in INCOMING_TYPES:
            self.counts.setdefault(t, [None] * 12)


@dataclass
class YearQuantityInput:
    """월별 입고·생산 실적/계획."""

    year: int
    inbound_qty: list[float | None] = field(default_factory=lambda: [None] * 12)
    production_qty: list[float | None] = field(default_factory=lambda: [None] * 12)


@dataclass
class ProjectionRates:
    """생산계획 연동 추정에 쓰는 연간 비율."""

    prod_per_inbound: float
    inspection_per_inbound: float
    type_shares: dict[str, float] = field(default_factory=dict)


@dataclass
class IncomingFrequencyResult:
    year: int
    summary_long: pd.DataFrame
    summary_wide: pd.DataFrame
    audit: list[str] = field(default_factory=list)


def _safe_sum(values: list[float | None]) -> float:
    nums = [v for v in values if v is not None]
    return float(sum(nums)) if nums else 0.0


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _month_list(data: list[float | None], n: int = 12) -> list[float | None]:
    padded = list(data[:n])
    while len(padded) < n:
        padded.append(None)
    return padded


def compute_type_shares(
    counts: dict[str, list[float | None]],
    months: int = 12,
) -> dict[str, float]:
    """연간 검사유형 비중 (샘플링/전수/무검사)."""
    totals = {t: _safe_sum(_month_list(counts.get(t, []), months)[:months]) for t in INCOMING_TYPES}
    grand = sum(totals.values())
    if grand <= 0:
        return {t: 0.0 for t in INCOMING_TYPES}
    return {t: totals[t] / grand for t in INCOMING_TYPES}


def compute_projection_rates(
    inbound: list[float | None],
    production: list[float | None],
    counts: dict[str, list[float | None]],
    months: int = 12,
) -> ProjectionRates:
    """실적 기반 연간 비율 산출."""
    inbound_slice = _month_list(inbound, months)[:months]
    production_slice = _month_list(production, months)[:months]
    count_slice = {t: _month_list(counts.get(t, []), months)[:months] for t in INCOMING_TYPES}

    total_inbound = _safe_sum(inbound_slice)
    total_production = _safe_sum(production_slice)
    total_inspection = _safe_sum(
        [
            _safe_sum(count_slice[t])
            for t in INCOMING_TYPES
        ]
    )

    prod_per_inbound = (
        total_production / total_inbound if total_inbound > 0 else 0.0
    )
    inspection_per_inbound = (
        total_inspection / total_inbound if total_inbound > 0 else 0.0
    )
    return ProjectionRates(
        prod_per_inbound=prod_per_inbound,
        inspection_per_inbound=inspection_per_inbound,
        type_shares=compute_type_shares(count_slice, months),
    )


def _project_month(
    production_qty: float | None,
    rates: ProjectionRates,
) -> tuple[dict[str, float | None], float | None, float | None]:
    """생산계획 기반 월별 추정."""
    if production_qty is None or rates.prod_per_inbound <= 0:
        empty = {t: None for t in INCOMING_TYPES}
        return empty, None, production_qty

    inbound = production_qty / rates.prod_per_inbound
    total_insp = inbound * rates.inspection_per_inbound
    by_type = {
        t: total_insp * rates.type_shares.get(t, 0.0)
        for t in INCOMING_TYPES
    }
    return by_type, inbound, production_qty


def analyze_incoming_frequency_year(
    pivot: YearPivotInput,
    quantities: YearQuantityInput,
    projection_rates: ProjectionRates | None = None,
    projection_start_month: int | None = None,
) -> IncomingFrequencyResult:
    """단일 연도 입고검사 발생빈도 분석."""
    audit: list[str] = []
    year = pivot.year

    rates = projection_rates or compute_projection_rates(
        quantities.inbound_qty,
        quantities.production_qty,
        pivot.counts,
        months=pivot.actual_months,
    )

    start_proj = projection_start_month
    if start_proj is None:
        start_proj = pivot.actual_months + 1
        if start_proj > 12:
            start_proj = 13

    monthly: dict[str, Any] = {f"insp_{t}": [None] * 12 for t in INCOMING_TYPES}
    monthly["insp_total"] = [None] * 12
    monthly["inbound_qty"] = _month_list(quantities.inbound_qty)
    monthly["production_qty"] = _month_list(quantities.production_qty)

    for idx in range(12):
        month = idx + 1
        use_projection = month >= start_proj

        if not use_projection:
            actual = {
                t: pivot.counts.get(t, [None] * 12)[idx]
                for t in INCOMING_TYPES
            }
            if any(v is not None for v in actual.values()):
                for t in INCOMING_TYPES:
                    monthly[f"insp_{t}"][idx] = actual[t]
                monthly["insp_total"][idx] = _safe_sum([actual[t] for t in INCOMING_TYPES])
                if monthly["inbound_qty"][idx] is None and monthly["production_qty"][idx] is not None:
                    if rates.prod_per_inbound > 0:
                        monthly["inbound_qty"][idx] = (
                            monthly["production_qty"][idx] / rates.prod_per_inbound
                        )
                continue

        by_type, inbound, production = _project_month(
            monthly["production_qty"][idx],
            rates,
        )
        if inbound is not None:
            monthly["inbound_qty"][idx] = inbound
        for t in INCOMING_TYPES:
            monthly[f"insp_{t}"][idx] = by_type[t]
        monthly["insp_total"][idx] = _safe_sum([by_type[t] for t in INCOMING_TYPES])
        audit.append(f"{year}년 {month}월: 생산계획 연동 추정 적용")

    monthly["prod_per_inbound"] = [
        _safe_div(monthly["production_qty"][i], monthly["inbound_qty"][i])
        for i in range(12)
    ]
    for t in INCOMING_TYPES:
        monthly[f"insp_per_inbound_{t}"] = [
            _safe_div(monthly[f"insp_{t}"][i], monthly["inbound_qty"][i])
            for i in range(12)
        ]
    monthly["insp_per_inbound_total"] = [
        _safe_div(monthly["insp_total"][i], monthly["inbound_qty"][i])
        for i in range(12)
    ]

    long_rows: list[dict[str, Any]] = []
    metrics = [
        ("입고검사 건수", "건", "insp_", INCOMING_TYPES + ("합계",)),
        ("입고수량(부품)", "EA", ("inbound_qty",), (None,)),
        ("생산수량(완제품)", "대", ("production_qty",), (None,)),
        ("생산수량/입고수량", "%", ("prod_per_inbound",), (None,)),
        ("입고검사/부품수량", "%", ("insp_per_inbound_",), INCOMING_TYPES + ("합계",)),
    ]

    for metric, unit, prefix, types in metrics:
        if metric == "입고검사 건수":
            for t in INCOMING_TYPES:
                values = monthly[f"insp_{t}"]
                long_rows.append(_summary_row(year, metric, unit, t, values, rates.type_shares.get(t)))
            long_rows.append(
                _summary_row(year, metric, unit, "합계", monthly["insp_total"], 1.0)
            )
        elif metric == "입고검사/부품수량":
            for t in INCOMING_TYPES:
                values = monthly[f"insp_per_inbound_{t}"]
                long_rows.append(_summary_row(year, metric, unit, t, values, None))
            long_rows.append(
                _summary_row(year, metric, unit, "합계", monthly["insp_per_inbound_total"], None)
            )
        else:
            key = prefix[0]
            values = monthly[key]
            long_rows.append(_summary_row(year, metric, unit, "", values, None))

    summary_long = pd.DataFrame(long_rows)
    summary_wide = _to_wide(summary_long)
    return IncomingFrequencyResult(
        year=year,
        summary_long=summary_long,
        summary_wide=summary_wide,
        audit=audit,
    )


def _summary_row(
    year: int,
    metric: str,
    unit: str,
    inspection_type: str,
    monthly_values: list[float | None],
    type_share: float | None,
) -> dict[str, Any]:
    nums = [v for v in monthly_values if v is not None]
    annual_total = float(sum(nums)) if nums else None
    monthly_avg = annual_total / len(nums) if nums and annual_total is not None else None
    row: dict[str, Any] = {
        "year": year,
        "metric": metric,
        "unit": unit,
        "inspection_type": inspection_type,
        "annual_total": annual_total,
        "monthly_avg": monthly_avg,
        "type_share": type_share,
    }
    for i, col in enumerate(MONTH_COLS):
        row[col] = monthly_values[i]
    return row


def _to_wide(summary_long: pd.DataFrame) -> pd.DataFrame:
    if summary_long.empty:
        return summary_long.copy()
    id_cols = ["year", "metric", "unit", "inspection_type", "annual_total", "monthly_avg", "type_share"]
    return summary_long[id_cols + MONTH_COLS].copy()


def _detect_pivot_month_columns(df: pd.DataFrame) -> list[int]:
    """Pivot 헤더 행(1~12월)의 컬럼 인덱스 탐지."""
    for _, row in df.fillna("").iterrows():
        month_cols: list[tuple[int, int]] = []
        for idx, val in enumerate(row.tolist()):
            try:
                month = int(float(val))
            except (TypeError, ValueError):
                continue
            if 1 <= month <= 12:
                month_cols.append((month, idx))
        if len(month_cols) >= 3:
            month_cols.sort(key=lambda x: x[0])
            ordered: list[int | None] = [None] * 12
            for month, idx in month_cols:
                ordered[month - 1] = idx
            return ordered
    return [i for i in range(1, 13)]


def parse_pivot_sheet(df: pd.DataFrame, year: int) -> YearPivotInput:
    """'24년 Pivot' / '25년 Pivot' 시트 파싱."""
    result = YearPivotInput(year=year)
    if df.empty:
        return result

    raw = df.copy().fillna("")
    month_col_indices = _detect_pivot_month_columns(raw)
    type_rows: dict[str, list[float | None]] = {}
    month_count = 0

    for _, row in raw.iterrows():
        label = ""
        for col_idx in range(min(3, len(row))):
            text = str(row.iloc[col_idx]).strip()
            if text in INCOMING_TYPES:
                label = text
                break
        if label not in INCOMING_TYPES:
            continue
        values: list[float | None] = [None] * 12
        filled = 0
        for month_idx, col_idx in enumerate(month_col_indices[:12]):
            if col_idx is None or col_idx >= len(row):
                continue
            try:
                values[month_idx] = float(row.iloc[col_idx])
                filled += 1
            except (TypeError, ValueError):
                continue
        if filled:
            type_rows[label] = values
            month_count = max(month_count, filled)

    for t in INCOMING_TYPES:
        result.counts[t] = type_rows.get(t, [None] * 12)
    result.actual_months = _trim_partial_tail_month(result.counts) or month_count
    if result.actual_months < month_count:
        for t in INCOMING_TYPES:
            for idx in range(result.actual_months, 12):
                result.counts[t][idx] = None
    return result


def _trim_partial_tail_month(counts: dict[str, list[float | None]]) -> int:
    """마지막 월이 미집계(급감)이면 실적 월수에서 제외."""
    monthly_totals: list[float] = []
    for i in range(12):
        vals = [counts.get(t, [None] * 12)[i] for t in INCOMING_TYPES]
        nums = [v for v in vals if v is not None]
        monthly_totals.append(sum(nums) if nums else 0.0)

    last_idx = max((i for i, t in enumerate(monthly_totals) if t > 0), default=-1)
    if last_idx <= 0:
        return 0

    prev = [t for t in monthly_totals[:last_idx] if t > 0]
    prev_avg = sum(prev) / len(prev) if prev else monthly_totals[last_idx]
    if prev_avg > 0 and monthly_totals[last_idx] < prev_avg * 0.2:
        return last_idx
    return last_idx + 1


def parse_production_plan_sheet(df: pd.DataFrame, year: int) -> YearQuantityInput:
    """'생산계획 연동' 시트에서 생산수량 월별 추출."""
    result = YearQuantityInput(year=year)
    if df.empty:
        return result

    year_token = str(year)

    for _, row in df.iterrows():
        row_text = " ".join(str(v) for v in row.tolist())
        first = str(row.iloc[0]).strip()
        if year_token not in row_text and year_token not in first:
            continue
        if "생산" not in row_text and "완제품" not in row_text:
            continue
        nums: list[float] = []
        for val in row.iloc[1:]:
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if 1000 <= num:
                nums.append(num)
        if len(nums) >= 6:
            for i, v in enumerate(nums[:12]):
                result.production_qty[i] = v
            return result

    for _, row in df.iterrows():
        first = str(row.iloc[0]).strip()
        if "생산수량" not in first and "완제품" not in first:
            continue
        nums = []
        for val in row.iloc[1:]:
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if 1000 <= num:
                nums.append(num)
        if len(nums) >= 6:
            for i, v in enumerate(nums[:12]):
                result.production_qty[i] = v
            break
    return result


def _extract_monthly_values(row: pd.Series, start_col: int = 6) -> list[float | None]:
    nums: list[float | None] = []
    for val in row.iloc[start_col : start_col + 12]:
        try:
            nums.append(float(val))
        except (TypeError, ValueError):
            nums.append(None)
    while len(nums) < 12:
        nums.append(None)
    return nums


def parse_inbound_production_from_analysis(
    df: pd.DataFrame,
    year: int,
) -> YearQuantityInput:
    """분석 시트에서 입고/생산 실적 행 추출 (이미 산출된 통합문서 재파싱)."""
    result = YearQuantityInput(year=year)
    if df.empty:
        return result

    raw = df.fillna("")
    year_token = f"{year}년"
    in_year = False

    for _, row in raw.iterrows():
        first = str(row.iloc[0]).strip()
        if first.startswith(year_token):
            in_year = True
            continue
        if in_year and first.endswith("년") and year_token not in first:
            break
        if not in_year:
            continue

        if first.startswith("입고수량") and "/" not in first:
            result.inbound_qty = _extract_monthly_values(row)
        elif first.startswith("생산수량") and "/" not in first:
            result.production_qty = _extract_monthly_values(row)

    return result


def analyze_workbook_sheets(
    sheets: dict[str, pd.DataFrame],
    years: list[int] | None = None,
    projection_overrides: dict[int, ProjectionRates] | None = None,
    use_raw: bool = True,
) -> pd.DataFrame:
    """근거 통합문서 시트 dict → 연도별 분석 결합."""
    target_years = years or [2024, 2025]
    frames: list[pd.DataFrame] = []

    def _find_sheet(*keywords: str) -> pd.DataFrame | None:
        for name, frame in sheets.items():
            lowered = name.lower()
            if all(k.lower() in lowered or k in name for k in keywords):
                return frame
        return None

    plan_sheet = _find_sheet("생산계획")
    analysis_sheet = _find_sheet("입고검사", "발생빈도")

    if use_raw:
        from quality_mh.incoming_raw_extractor import extract_incoming_raw, find_inspection_list_sheet

        for year in target_years:
            list_df = find_inspection_list_sheet(sheets, year)
            if list_df is None:
                continue
            raw = extract_incoming_raw(list_df, year, production_plan_df=plan_sheet)
            rates = (projection_overrides or {}).get(year)
            result = analyze_incoming_frequency_year(
                pivot=raw.pivot,
                quantities=raw.quantities,
                projection_rates=rates,
            )
            frames.append(result.summary_long)
    else:
        pivot_by_year = {
            2024: _find_sheet("24", "pivot"),
            2025: _find_sheet("25", "pivot"),
        }
        for year in target_years:
            pivot_df = pivot_by_year.get(year)
            if pivot_df is None:
                continue
            pivot = parse_pivot_sheet(pivot_df, year)
            quantities = YearQuantityInput(year=year)
            if analysis_sheet is not None:
                quantities = parse_inbound_production_from_analysis(analysis_sheet, year)
            if plan_sheet is not None:
                plan = parse_production_plan_sheet(plan_sheet, year)
                for i in range(12):
                    if quantities.production_qty[i] is None:
                        quantities.production_qty[i] = plan.production_qty[i]
            rates = (projection_overrides or {}).get(year)
            result = analyze_incoming_frequency_year(
                pivot=pivot,
                quantities=quantities,
                projection_rates=rates,
            )
            frames.append(result.summary_long)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def analyze_workbook_sheets_with_raw(
    sheets: dict[str, pd.DataFrame],
    years: list[int] | None = None,
    projection_overrides: dict[int, ProjectionRates] | None = None,
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame], dict[int, pd.DataFrame], list[str]]:
    """Raw 추출본 + pivot + 집계 결과 반환."""
    from quality_mh.incoming_raw_extractor import (
        extract_incoming_raw,
        find_inspection_list_sheet,
        pivot_to_dataframe,
    )

    target_years = years or [2024, 2025]
    raw_by_year: dict[int, pd.DataFrame] = {}
    pivot_by_year: dict[int, pd.DataFrame] = {}
    audit: list[str] = []
    frames: list[pd.DataFrame] = []

    plan_sheet = None
    for name, frame in sheets.items():
        if "생산계획" in name and "분석" not in name:
            plan_sheet = frame
            break

    for year in target_years:
        list_df = find_inspection_list_sheet(sheets, year)
        if list_df is None:
            audit.append(f"{year}년 검사빈도 리스트 시트 없음")
            continue
        raw = extract_incoming_raw(list_df, year, production_plan_df=plan_sheet)
        raw_by_year[year] = raw.records
        pivot_by_year[year] = pivot_to_dataframe(raw.pivot)
        audit.extend(raw.audit)

        rates = (projection_overrides or {}).get(year)
        result = analyze_incoming_frequency_year(
            pivot=raw.pivot,
            quantities=raw.quantities,
            projection_rates=rates,
        )
        frames.append(result.summary_long)

    summary = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return summary, raw_by_year, pivot_by_year, audit


def to_frequency_dataframe(summary_long: pd.DataFrame, factory_name: str = "천안") -> pd.DataFrame:
    """MH 파이프라인용 frequency_df 변환."""
    if summary_long.empty:
        return pd.DataFrame()

    rows = []
    target = summary_long[summary_long["metric"] == "입고검사 건수"].copy()
    for _, r in target.iterrows():
        insp_type = r.get("inspection_type", "")
        if insp_type in ("", "합계"):
            continue
        for i, col in enumerate(MONTH_COLS, start=1):
            qty = r.get(col)
            if qty is None or (isinstance(qty, float) and pd.isna(qty)):
                continue
            rows.append({
                "factory_name": factory_name,
                "domain": "입고",
                "inspection_type": insp_type,
                "line_name": "",
                "inspection_name": "입고검사",
                "year": int(r["year"]),
                "month": i,
                "quantity": float(qty),
                "frequency_value": float(qty),
                "applied_frequency_rule": "FREQ-INCOMING-INSPECTION",
                "validation_status": "OK",
                "validation_message": "",
            })
    return pd.DataFrame(rows)
