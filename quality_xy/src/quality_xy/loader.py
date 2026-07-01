"""파일 로드 및 컬럼/시간 자동 탐지."""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

TIME_KEYWORDS = (
    "시간", "시각", "일시", "날짜", "date", "time", "datetime", "timestamp", "발생", "검사일", "생산일",
)
KEY_KEYWORDS = (
    "바코드", "barcode", "lot", "로트", "serial", "시리얼", "제품", "품번", "part", "설비", "라인", "line",
    "작업지시", "wo", "order",
)


def normalize_key_value(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    text = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    return text.upper()


def load_dataframe(source: Path | BytesIO, sheet_name: str | int | None = 0) -> pd.DataFrame:
    if isinstance(source, BytesIO):
        name = getattr(source, "name", "") or ""
        if name.lower().endswith(".csv"):
            source.seek(0)
            return pd.read_csv(source)
        source.seek(0)
        return pd.read_excel(source, sheet_name=sheet_name or 0, engine="openpyxl")

    path = Path(source)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path, sheet_name=sheet_name or 0, engine="openpyxl")


def list_sheets(source: Path | BytesIO) -> list[str]:
    if isinstance(source, BytesIO):
        source.seek(0)
        xl = pd.ExcelFile(source, engine="openpyxl")
        return list(xl.sheet_names)
    path = Path(source)
    if path.suffix.lower() == ".csv":
        return ["CSV"]
    xl = pd.ExcelFile(path, engine="openpyxl")
    return list(xl.sheet_names)


def score_column_name(col: str, keywords: tuple[str, ...]) -> float:
    lowered = col.lower().replace(" ", "")
    for i, kw in enumerate(keywords):
        if kw.lower() in lowered:
            return 1.0 - i * 0.01
    return 0.0


def detect_datetime_column(df: pd.DataFrame) -> str | None:
    best_col: str | None = None
    best_score = 0.0
    for col in df.columns:
        name_score = score_column_name(str(col), TIME_KEYWORDS)
        parsed = pd.to_datetime(df[col], errors="coerce")
        valid_ratio = parsed.notna().mean() if len(parsed) else 0.0
        score = name_score * 0.4 + valid_ratio * 0.6
        if score > best_score and valid_ratio >= 0.5:
            best_score = score
            best_col = str(col)
    return best_col


def detect_key_columns(df: pd.DataFrame, max_cols: int = 8) -> list[str]:
    scored: list[tuple[float, str]] = []
    for col in df.columns:
        series = df[col].map(normalize_key_value).dropna()
        if series.empty:
            continue
        unique_ratio = series.nunique() / max(len(series), 1)
        if unique_ratio < 0.01 or unique_ratio > 0.98:
            continue
        name_score = score_column_name(str(col), KEY_KEYWORDS)
        overlap_score = min(unique_ratio, 1 - unique_ratio) * 2
        scored.append((name_score * 0.5 + overlap_score * 0.5, str(col)))
    scored.sort(reverse=True)
    return [col for _, col in scored[:max_cols]]


def columns_for_linking(df: pd.DataFrame, max_cols: int = 20) -> list[str]:
    """연결 키 후보 — 이름 기반 키(바코드 등)는 고유값 비율이 높아도 포함."""
    base = detect_key_columns(df, max_cols=max_cols)
    seen = set(base)
    extra: list[str] = []
    for col in df.columns:
        col_s = str(col)
        if col_s in seen:
            continue
        if score_column_name(col_s, KEY_KEYWORDS) <= 0:
            continue
        series = df[col].map(normalize_key_value).dropna()
        if len(series) < 2 or series.nunique() < 2:
            continue
        extra.append(col_s)
        seen.add(col_s)
    return base + extra


def parse_datetime_series(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_datetime(df[col], errors="coerce")


class DatasetProfile:
    def __init__(self, name: str, df: pd.DataFrame) -> None:
        self.name = name
        self.df = df.copy()
        self.datetime_col = detect_datetime_column(df)
        self.suggested_keys = columns_for_linking(df)

    def key_values(self, col: str) -> set[str]:
        return set(self.df[col].map(normalize_key_value).dropna())
