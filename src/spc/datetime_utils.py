"""MES/QMS 날짜·시간 파싱 (Excel serial, 시각만, 파일명 날짜 등)."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

# Excel serial: 2026-01-01 ≈ 46023
_EXCEL_DATE_MIN = 30000
_UNIX_SEC_MIN = 1_000_000_000  # ~2001
_UNIX_MS_MIN = 1_000_000_000_000
_SECONDS_PER_DAY = 86400


def date_from_text(text: str) -> pd.Timestamp | None:
    """문자열/파일명에서 YYYYMMDD 또는 YYYYMMDDHHMMSS 추출."""
    if not text:
        return None
    m = re.search(r"(20\d{12})", str(text))  # 14자리
    if m:
        s = m.group(1)
        return pd.Timestamp(
            year=int(s[0:4]), month=int(s[4:6]), day=int(s[6:8]),
            hour=int(s[8:10]), minute=int(s[10:12]), second=int(s[12:14]),
        )
    m = re.search(r"(20\d{6})", str(text))  # 8자리 날짜
    if m:
        s = m.group(1)
        return pd.Timestamp(year=int(s[0:4]), month=int(s[4:6]), day=int(s[6:8]))
    return None


def date_from_filename(path: Path | str) -> pd.Timestamp | None:
    return date_from_text(Path(path).stem)


def parse_timestamp_series(
    series: pd.Series,
    ref_date: pd.Timestamp | None = None,
) -> pd.Series:
    """
    MES/QMS timestamp 컬럼을 올바른 datetime으로 변환.

    - 이미 datetime → 유지
    - 문자열 날짜 → pd.to_datetime
    - Excel serial (30000~60000) → origin 1899-12-30
    - Unix 초/밀리초 → unit s/ms
    - 0~86400 (또는 0~1) → 하루 중 시각 + ref_date(파일명 등)
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        out = series
        if ref_date is not None and out.dt.year.mode().iloc[0] == 1970:
            return _apply_time_only(out, ref_date)
        return out

    # 문자열
    as_str = series.astype(str).str.strip()
    parsed = pd.to_datetime(as_str, errors="coerce")
    if parsed.notna().mean() > 0.8 and _valid_year_ratio(parsed) > 0.8:
        return parsed

    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return parsed

    med = float(numeric.dropna().median())

    # Excel 일자+시간 serial
    if _EXCEL_DATE_MIN <= med <= 60000:
        return pd.to_datetime(numeric, unit="D", origin="1899-12-30", errors="coerce")

    # Unix timestamp
    if med >= _UNIX_MS_MIN:
        return pd.to_datetime(numeric, unit="ms", errors="coerce")
    if med >= _UNIX_SEC_MIN:
        return pd.to_datetime(numeric, unit="s", errors="coerce")

    # 하루 중 시각 (초 또는 Excel time fraction)
    if med < _SECONDS_PER_DAY * 2:
        if ref_date is None:
            return parsed  # fallback
        if med <= 1:
            seconds = numeric * _SECONDS_PER_DAY
        else:
            seconds = numeric
        base = pd.Timestamp(ref_date.normalize())
        return base + pd.to_timedelta(seconds, unit="s")

    return parsed


def _valid_year_ratio(ts: pd.Series) -> float:
    valid = ts.dropna()
    if len(valid) == 0:
        return 0.0
    return (valid.dt.year >= 2000).mean()


def _apply_time_only(ts: pd.Series, ref_date: pd.Timestamp) -> pd.Series:
    base = pd.Timestamp(ref_date.normalize())
    seconds = ts.dt.hour * 3600 + ts.dt.minute * 60 + ts.dt.second
    return base + pd.to_timedelta(seconds, unit="s")


def enrich_timestamp_from_source(df: pd.DataFrame) -> pd.DataFrame:
    """source(파일명)에서 날짜를 추출해 timestamp 보정."""
    if "timestamp" not in df.columns or "source" not in df.columns:
        return df

    df = df.copy()
    years = df["timestamp"].dropna()
    if len(years) and _valid_year_ratio(years) > 0.8:
        return df

    def fix_row(row):
        ts = row.get("timestamp")
        src = row.get("source", "")
        ref = date_from_text(str(src))
        if ref is None or pd.isna(ts):
            return ts
        if isinstance(ts, pd.Timestamp) and ts.year >= 2000:
            return ts
        if isinstance(ts, pd.Timestamp) and ts.year == 1970:
            base = ref.normalize()
            return base + pd.Timedelta(
                hours=ts.hour, minutes=ts.minute, seconds=ts.second
            )
        return parse_timestamp_series(pd.Series([ts]), ref).iloc[0]

    df["timestamp"] = df.apply(fix_row, axis=1)
    return df
