"""컬럼명 정규화 및 매핑."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from quality_mh.rule_loader import load_column_mapping


def normalize_header(name: str) -> str:
    return re.sub(r"\s+", "", str(name).strip().lower())


def build_alias_map(mapping: dict[str, Any] | None = None) -> dict[str, str]:
    data = mapping or load_column_mapping()
    alias_map: dict[str, str] = {}
    for standard, aliases in data.get("standard_columns", {}).items():
        alias_map[normalize_header(standard)] = standard
        for alias in aliases:
            alias_map[normalize_header(alias)] = standard
    return alias_map


def rename_columns(df: pd.DataFrame, mapping: dict[str, Any] | None = None) -> pd.DataFrame:
    alias_map = build_alias_map(mapping)
    rename_dict: dict[str, str] = {}
    for col in df.columns:
        norm = normalize_header(col)
        if norm in alias_map:
            rename_dict[col] = alias_map[norm]
    return df.rename(columns=rename_dict)


def detect_mapped_columns(df: pd.DataFrame, mapping: dict[str, Any] | None = None) -> dict[str, str]:
    alias_map = build_alias_map(mapping)
    found: dict[str, str] = {}
    for col in df.columns:
        norm = normalize_header(col)
        if norm in alias_map:
            found[col] = alias_map[norm]
    return found
