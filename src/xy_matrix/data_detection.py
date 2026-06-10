"""
Raw 데이터 구조 자동 인식: 인자 유형 행, Y/X 컬럼, 계량·범주·계수 판별.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Union

import numpy as np
import pandas as pd

from src.xy_matrix.column_aliases import (
    FACTOR_TYPE_CELL_HINTS,
    column_name_suggests_meta,
    column_name_suggests_x_cat,
    column_name_suggests_x_quant,
    column_name_suggests_y,
)
from src.xy_matrix.constants import (
    DATETIME_NAME_KEYWORDS,
    TYPE_CATEGORICAL,
    TYPE_CONTINUOUS,
    TYPE_COUNT,
    X_CAT_KEYWORDS,
    X_GENERIC_KEYWORDS,
    X_QUANT_KEYWORDS,
    Y_TYPE_KEYWORDS,
)

logger = logging.getLogger(__name__)

DataSource = Union[str, Path, pd.DataFrame]


def _normalize_cell(val: Any) -> str:
    if pd.isna(val):
        return ""
    return re.sub(r"\s+", "", str(val).strip().lower())


def _cell_matches_keywords(cell: str, keywords: tuple[str, ...]) -> bool:
    if not cell:
        return False
    for kw in keywords:
        if kw in cell or cell == kw.replace(" ", ""):
            return True
    return False


def _classify_subtype_cell(cell: str) -> str | None:
    """보조 행(셀별 계량형/범주형만) → x_quant / x_cat."""
    c = _normalize_cell(cell)
    if not c:
        return None
    if "범주" in c or c in ("범주형", "이산", "이산형", "categorical"):
        return "x_cat"
    if "계량" in c or "연속" in c or c in ("계량형", "연속형", "numeric"):
        return "x_quant"
    return None


def _classify_type_cell(cell: str) -> str | None:
    """인자 유형 행 셀 → y / x_quant / x_cat / x_generic / None."""
    sub = _classify_subtype_cell(cell)
    if sub and not _cell_matches_keywords(cell, Y_TYPE_KEYWORDS + X_GENERIC_KEYWORDS):
        return sub

    if _cell_matches_keywords(cell, Y_TYPE_KEYWORDS):
        if "x" in cell and "y" not in cell:
            return None
        return "y"
    if _cell_matches_keywords(cell, X_QUANT_KEYWORDS):
        return "x_quant"
    if _cell_matches_keywords(cell, X_CAT_KEYWORDS):
        return "x_cat"
    if _cell_matches_keywords(cell, X_GENERIC_KEYWORDS):
        return "x_generic"
    c = cell.replace(" ", "")
    if c in ("y", "결과y") or (c.endswith("y") and "x" not in c and "결과" in c):
        return "y"
    if c in ("x",) or (c.endswith("x") and "계량" not in c and "범주" not in c):
        return "x_generic"
    return None


def _is_pure_subtype_row(row: pd.Series) -> bool:
    """삭제 대상이었던 '계량형/범주형' 전용 보조 행."""
    subtype = 0
    roles = 0
    non_empty = 0
    for cell in row:
        if pd.isna(cell) or str(cell).strip() == "":
            continue
        non_empty += 1
        nc = _normalize_cell(cell)
        if _classify_subtype_cell(nc):
            subtype += 1
        if _classify_type_cell(nc) in ("y", "x_generic"):
            roles += 1
    return non_empty >= 2 and subtype >= max(2, non_empty // 2) and roles == 0


def _is_numeric_index_like(name: str) -> bool:
    s = str(name).strip()
    if not s or s.startswith("Unnamed") or s.startswith("col_"):
        return True
    if re.fullmatch(r"-?\d+(\.0)?", s):
        return True
    return False


def _score_name_row(row: pd.Series) -> float:
    """인자명 행 적합도 (높을수록 실제 컬럼명 행)."""
    if _is_pure_subtype_row(row):
        return -10.0
    score = 0.0
    non_empty = 0
    for cell in row:
        if pd.isna(cell) or str(cell).strip() == "":
            continue
        non_empty += 1
        text = str(cell).strip()
        nc = _normalize_cell(text)
        if _classify_type_cell(nc) in ("y", "x_quant", "x_cat", "x_generic"):
            score -= 2
        if _is_numeric_index_like(text):
            score -= 3
        elif re.search(r"[가-힣a-zA-Z]", text):
            score += 4
        if column_name_suggests_y(text) or column_name_suggests_x_quant(text):
            score += 2
    if non_empty == 0:
        return -20.0
    return score / non_empty


def _invalid_y_column_name(name: str) -> bool:
    s = str(name).strip().lower()
    if not s or s in ("nan", "none", "nat") or s.startswith("unnamed"):
        return True
    if _is_numeric_index_like(name):
        return True
    if re.fullmatch(r"col_\d+", s):
        return True
    return False


def _pick_leftmost_y_column(columns: list[str], excluded: list[str]) -> str | None:
    """
    품질 Raw 시트 관례: 맨 왼쪽 분석 대상 열 = Y인자(품질 특성).
    날짜·메타·순번(0,1,2…)·빈 열은 건너뜀.
    """
    for col in columns:
        if col in excluded or column_name_suggests_meta(col):
            continue
        if _invalid_y_column_name(col):
            continue
        return col
    for col in columns:
        if col not in excluded:
            return col
    return None


def _apply_leftmost_y_rule(
    columns: list[str],
    excluded: list[str],
    y_columns: list[str],
) -> tuple[list[str], str | None]:
    """유형행 Y 표기와 무관하게 맨 왼쪽 유효 열을 Y로 고정."""
    left_y = _pick_leftmost_y_column(columns, excluded)
    if not left_y:
        return y_columns, None
    prev = list(y_columns)
    if prev != [left_y]:
        if prev:
            logger.info(
                "Y인자: 맨 왼쪽 열 '%s' 사용 (유형행 지정 %s 대신)",
                left_y,
                prev,
            )
        else:
            logger.info("Y인자: 맨 왼쪽 열 '%s' 자동 지정", left_y)
    return [left_y], left_y


def _is_datetime_column(name: str, series: pd.Series) -> bool:
    name_l = str(name).lower()
    if any(kw in name_l for kw in DATETIME_NAME_KEYWORDS):
        return True
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if not pd.api.types.is_object_dtype(series) and not pd.api.types.is_string_dtype(series):
        return False
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    if len(series) > 0 and parsed.notna().mean() > 0.85:
        return True
    return False


def infer_variable_type(series: pd.Series, declared: str | None = None) -> str:
    """
    명시 유형이 있으면 사용, 없으면 데이터 기반 추론 (X용: 계량형/범주형).
    """
    if declared in (TYPE_CONTINUOUS, TYPE_CATEGORICAL):
        return declared

    s = series.dropna()
    n = len(s)
    if n == 0:
        return TYPE_CATEGORICAL

    if pd.api.types.is_numeric_dtype(s):
        n_unique = s.nunique()
        ratio = n_unique / n if n > 0 else 0
        if ratio >= 0.05 or n_unique >= 20:
            return TYPE_CONTINUOUS
        if ratio < 0.05 and n_unique < 20:
            return TYPE_CATEGORICAL
        return TYPE_CONTINUOUS

    return TYPE_CATEGORICAL


def detect_y_type(y_series: pd.Series) -> str:
    """
    Y인자 유형: 계량형(연속), 계수형(이산), 분석불가.
    """
    s = y_series.dropna()
    if len(s) == 0:
        raise ValueError("Y인자에 유효한 데이터가 없습니다.")

    n_unique = s.nunique()

    if pd.api.types.is_numeric_dtype(s):
        if n_unique > 10:
            return TYPE_CONTINUOUS
        if 2 <= n_unique <= 10:
            return TYPE_COUNT
        if n_unique == 1:
            raise ValueError("Y인자가 단일 값만 포함합니다.")
        return TYPE_COUNT

    if n_unique <= 5:
        return TYPE_COUNT
    logger.warning(
        "Y인자 '%s'는 범주 수(%d)가 많아 계수형 분석이 부적합할 수 있습니다.",
        y_series.name,
        n_unique,
    )
    if n_unique <= 15:
        return TYPE_COUNT
    return "분석불가"


def _count_type_roles(row: pd.Series) -> tuple[int, int, dict[int, str]]:
    """(y+x 역할 수, y 수, {열인덱스: 역할})."""
    roles: dict[int, str] = {}
    for j, cell in enumerate(row):
        role = _classify_type_cell(_normalize_cell(cell))
        if role in ("y", "x_quant", "x_cat", "x_generic"):
            roles[j] = role
    y_count = sum(1 for r in roles.values() if r == "y")
    return len(roles), y_count, roles


def _resolve_header_layout(
    raw: pd.DataFrame,
    max_scan: int = 40,
) -> tuple[int | None, int | None, int | None, int, dict[int, str], dict[str, str]]:
    """
    (type_row, subtype_row, name_row, data_start, col_roles, col_declared) 반환.

    지원 레이아웃:
    - [유형행] → [인자명행] → 데이터  (기본)
    - [인자명행] → [유형행] → 데이터  (보조 행 삭제 후 흔함)
    - [유형행] → [보조:계량/범주] → [인자명행] → 데이터 (구형, 보조 행 있음)
    """
    best: tuple[float, int | None, int | None, int | None, int, dict, dict] | None = None

    limit = min(max_scan, len(raw) - 1)
    for i in range(limit):
        row_i = raw.iloc[i]
        row_j = raw.iloc[i + 1] if i + 1 < len(raw) else None
        if row_j is None:
            continue

        name_score_i = _score_name_row(row_i)
        name_score_j = _score_name_row(row_j)
        roles_i, y_i, map_i = _count_type_roles(row_i)
        roles_j, y_j, map_j = _count_type_roles(row_j)
        subtype_i = _is_pure_subtype_row(row_i)
        subtype_j = _is_pure_subtype_row(row_j) if row_j is not None else False

        candidates: list[tuple[float, int | None, int | None, int, dict, dict]] = []

        # 유형 → 인자명
        if roles_i >= 1 and y_i >= 1 and not subtype_i:
            ns = name_score_j
            if ns >= 1.0 and not subtype_j:
                candidates.append((roles_i * 3 + y_i * 5 + ns * 2, i, None, i + 1, i + 2, map_i, {}))

        # 인자명 → 유형 (보조 행 제거 후)
        if roles_j >= 1 and y_j >= 1 and name_score_i >= 1.0 and not subtype_i:
            candidates.append((roles_j * 3 + y_j * 5 + name_score_i * 2, i + 1, None, i, i + 2, map_j, {}))

        # 유형 → 보조(계량/범주) → 인자명
        if i + 2 < len(raw):
            row_k = raw.iloc[i + 2]
            name_score_k = _score_name_row(row_k)
            if roles_i >= 1 and y_i >= 1 and subtype_j and name_score_k >= 1.0:
                declared: dict[str, str] = {}
                subtype_map: dict[int, str] = {}
                for j, cell in enumerate(row_j):
                    st = _classify_subtype_cell(_normalize_cell(cell))
                    if st:
                        subtype_map[j] = st
                candidates.append((
                    roles_i * 3 + y_i * 5 + name_score_k * 2 + 5,
                    i, i + 1, i + 2, i + 3, map_i, subtype_map,
                ))

        for cand in candidates:
            if best is None or cand[0] > best[0]:
                best = cand

    if best is not None:
        _, t_idx, st_idx, n_idx, d_start, roles, subtype_map = best
        col_declared: dict[str, str] = {}
        if st_idx is not None and n_idx is not None:
            name_row = raw.iloc[n_idx]
            sub_row = raw.iloc[st_idx]
            for j in subtype_map:
                if j < len(name_row):
                    nm = str(name_row.iloc[j]).strip()
                    if nm and not _is_numeric_index_like(nm):
                        if subtype_map[j] == "x_cat":
                            col_declared[nm] = TYPE_CATEGORICAL
                        else:
                            col_declared[nm] = TYPE_CONTINUOUS
        return t_idx, st_idx, n_idx, d_start, roles, col_declared

    # 폴백: 인자명 행만 스캔
    best_name: tuple[float, int] | None = None
    for i in range(min(max_scan, len(raw))):
        sc = _score_name_row(raw.iloc[i])
        if sc >= 2.0 and (best_name is None or sc > best_name[0]):
            best_name = (sc, i)
    if best_name:
        n_idx = best_name[1]
        return None, None, n_idx, n_idx + 1, {}, {}

    return None, None, None, 0, {}, {}


def _load_raw(data_source: DataSource, sheet_name: str | int = 0) -> pd.DataFrame:
    if isinstance(data_source, pd.DataFrame):
        return data_source.copy()
    path = Path(data_source)
    if not path.exists():
        raise FileNotFoundError(f"데이터 파일을 찾을 수 없습니다: {path}")
    try:
        from src.spc.excel_reader import read_excel_auto
        return read_excel_auto(path, sheet_name=sheet_name, header=None)
    except Exception:
        return pd.read_excel(path, sheet_name=sheet_name, header=None, engine="openpyxl")


def auto_detect_data_structure(
    data_source: DataSource,
    sheet_name: str | int = 0,
    include_datetime: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """
    헤더·인자 유형 행을 자동 탐지하고 분석용 DataFrame과 구조 메타를 반환.
    """
    raw = _load_raw(data_source, sheet_name=sheet_name)
    type_row_idx, subtype_row_idx, name_row_idx, data_start_idx, col_roles, col_declared = (
        _resolve_header_layout(raw)
    )

    if name_row_idx is not None:
        name_row = raw.iloc[name_row_idx]
        type_row = raw.iloc[type_row_idx] if type_row_idx is not None else None

        columns: list[str] = []
        col_index_roles: dict[int, str] = (
            col_roles.copy()
            if isinstance(col_roles, dict)
            else {int(k): v for k, v in col_roles.items()}
        )

        for j, n_cell in enumerate(name_row):
            name = str(n_cell).strip() if pd.notna(n_cell) and str(n_cell).strip() else ""
            if name.lower() in ("nan", "none"):
                name = ""
            if not name or name.startswith("Unnamed") or _is_numeric_index_like(name):
                if type_row is not None and j < len(type_row):
                    alt = str(type_row.iloc[j]).strip()
                    if alt and not _classify_type_cell(_normalize_cell(alt)) and not _is_numeric_index_like(alt):
                        name = alt
                if not name or _is_numeric_index_like(name):
                    name = f"col_{j}"
            columns.append(name)

            if type_row is not None and j < len(type_row):
                role = _classify_type_cell(_normalize_cell(type_row.iloc[j]))
                if role:
                    col_index_roles[j] = role
                if role == "x_quant" and name not in col_declared:
                    col_declared[name] = TYPE_CONTINUOUS
                elif role == "x_cat" and name not in col_declared:
                    col_declared[name] = TYPE_CATEGORICAL

        if sum(1 for c in columns if _is_numeric_index_like(c)) > len(columns) * 0.5:
            raise ValueError(
                "인자명 행을 찾지 못했습니다. 컬럼명이 0,1,2… 로 읽혔습니다.\n"
                "Raw 시트: [인자명 행] 바로 아래(또는 위)에 [결과 Y / 계량형 X / 범주형 X] 행이 "
                "있는지 확인하세요. (계량형/범주형만 있는 보조 행은 삭제해도 됩니다.)"
            )

        df = raw.iloc[data_start_idx:].copy()
        df.columns = columns
        df = df.reset_index(drop=True)

        y_columns = [columns[j] for j, r in col_index_roles.items() if r == "y"]
        x_columns = [
            columns[j] for j, r in col_index_roles.items()
            if r in ("x_quant", "x_cat", "x_generic")
        ]
        header_row = type_row_idx if type_row_idx is not None else name_row_idx
        data_start_row = data_start_idx

        if type_row_idx is None:
            logger.info("인자 유형 행 없음 — 인자명·데이터 기반으로 Y/X 추론합니다.")
    else:
        logger.warning(
            "헤더 구조를 찾지 못했습니다. 상단 40행에서 인자명·유형 행을 확인하세요."
        )
        df = raw.copy()
        best_i, best_sc = 0, -999.0
        for i in range(min(40, len(raw))):
            sc = _score_name_row(raw.iloc[i])
            if sc > best_sc:
                best_sc, best_i = sc, i
        if best_sc >= 2.0:
            df.columns = [
                str(c).strip() if pd.notna(c) and str(c).strip() else f"col_{j}"
                for j, c in enumerate(raw.iloc[best_i])
            ]
            df = raw.iloc[best_i + 1:].copy().reset_index(drop=True)
            header_row = best_i
            data_start_row = best_i + 1
        else:
            df.columns = [str(c) for c in df.columns]
            header_row = 0
            data_start_row = 1
        y_columns = []
        x_columns = list(df.columns)
        col_declared = {}
        col_index_roles = {}

    for c in df.columns:
        converted = pd.to_numeric(df[c], errors="coerce")
        if converted.notna().sum() >= max(1, len(df) * 0.5):
            df[c] = converted

    excluded: list[str] = []
    if not include_datetime:
        for c in df.columns:
            if _is_datetime_column(c, df[c]):
                excluded.append(c)

    if not y_columns:
        left_y = _pick_leftmost_y_column(list(df.columns), excluded)
        if left_y:
            y_columns = [left_y]
        else:
            alias_y = [
                c for c in df.columns
                if c not in excluded and column_name_suggests_y(c)
            ]
            numeric_cols = [
                c for c in df.columns
                if c not in excluded and pd.api.types.is_numeric_dtype(df[c])
                and not column_name_suggests_meta(c)
            ]
            if alias_y:
                y_columns = [alias_y[0]]
            elif numeric_cols:
                y_columns = [numeric_cols[0]]
            else:
                raise ValueError(
                    "Y인자를 자동 탐지하지 못했습니다. y_column 인자로 지정하세요."
                )

    y_columns, selected_y = _apply_leftmost_y_rule(
        list(df.columns), excluded, y_columns
    )

    if not x_columns:
        x_columns = [
            c for c in df.columns
            if c not in y_columns and c not in excluded and not column_name_suggests_meta(c)
        ]

    x_columns = [
        c for c in x_columns
        if c not in y_columns and c not in excluded and not column_name_suggests_meta(c)
    ]

    y_types = {yc: detect_y_type(df[yc]) for yc in y_columns}
    x_types = {}
    for xc in x_columns:
        declared = col_declared.get(xc)
        if not declared:
            if column_name_suggests_x_cat(xc):
                declared = TYPE_CATEGORICAL
            elif column_name_suggests_x_quant(xc):
                declared = TYPE_CONTINUOUS
        x_types[xc] = infer_variable_type(df[xc], declared)

    structure = {
        "y_columns": y_columns,
        "y_types": y_types,
        "x_columns": x_columns,
        "x_types": x_types,
        "y_selection": "leftmost_column",
        "selected_y": selected_y or (y_columns[0] if y_columns else None),
        "header_row": header_row,
        "type_row": type_row_idx,
        "subtype_row": subtype_row_idx,
        "name_row": name_row_idx,
        "data_start_row": data_start_row,
        "excluded_columns": excluded,
        "layout_hint": (
            "인자명→유형→데이터"
            if name_row_idx is not None and type_row_idx is not None and name_row_idx < type_row_idx
            else "유형→인자명→데이터"
            if name_row_idx is not None and type_row_idx is not None
            else "인자명만"
            if type_row_idx is None and name_row_idx is not None
            else "미확인"
        ),
    }
    return df, structure
