"""Excel 파서 - 다공장/다역할 파일 흡수."""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from quality_mh.column_normalizer import detect_mapped_columns, rename_columns
from quality_mh.file_classifier import classify_excel_file
from quality_mh.models import FileAnalysisResult

logger = logging.getLogger(__name__)


def list_sheets(path: Path | BytesIO) -> list[str]:
    xl = pd.ExcelFile(path)
    return xl.sheet_names


def read_sheet(path: Path | BytesIO, sheet_name: str | int = 0, header_row: int | None = None) -> pd.DataFrame:
    if header_row is not None:
        return pd.read_excel(path, sheet_name=sheet_name, header=header_row)
    return _read_with_header_detection(path, sheet_name)


def _read_with_header_detection(path: Path | BytesIO, sheet_name: str | int) -> pd.DataFrame:
    preview = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=15)
    header_idx = 0
    for i in range(len(preview)):
        row_vals = [str(v).strip() for v in preview.iloc[i].tolist() if pd.notna(v)]
        if len(row_vals) >= 3:
            header_idx = i
            break
    df = pd.read_excel(path, sheet_name=sheet_name, header=header_idx)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    return df


def parse_excel_file(
    path: Path | BytesIO,
    file_name: str = "",
    sheet_name: str | int | None = None,
    mapping: dict[str, Any] | None = None,
) -> tuple[FileAnalysisResult, dict[str, pd.DataFrame]]:
    name = file_name or (path.name if isinstance(path, Path) else "uploaded.xlsx")
    sheets = list_sheets(path)
    classification = classify_excel_file(Path(name), sheets)

    parsed: dict[str, pd.DataFrame] = {}
    target_sheets = [sheet_name] if sheet_name is not None else sheets

    for sn in target_sheets:
        try:
            raw = read_sheet(path, sn)
            normalized = rename_columns(raw, mapping)
            normalized["source_file"] = name
            normalized["source_sheet"] = str(sn)
            if classification.factory_name and "factory_name" not in normalized.columns:
                normalized["factory_name"] = classification.factory_name
            parsed[str(sn)] = normalized
            classification.detected_columns[str(sn)] = list(detect_mapped_columns(raw, mapping).values())
        except Exception as exc:
            logger.warning("시트 읽기 실패 %s/%s: %s", name, sn, exc)

    return classification, parsed


def preview_sheet_structure(df: pd.DataFrame, n: int = 5) -> dict[str, Any]:
    return {
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "preview": df.head(n).to_dict(orient="records"),
        "row_count": len(df),
    }


def concat_normalized(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)
