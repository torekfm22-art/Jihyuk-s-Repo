"""
CTP 선정 및 SPC 관리도 유형 권고.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from src.xy_matrix.constants import (
    ENV_UNCONTROLLABLE_KEYWORDS,
    TYPE_CATEGORICAL,
    TYPE_CONTINUOUS,
)


def _is_environment_factor(name: str) -> bool:
    name_l = re.sub(r"\s+", "", str(name).lower())
    return any(kw in name_l for kw in ENV_UNCONTROLLABLE_KEYWORDS)


def infer_controllability(
    factor_names: list[str],
    controllability: dict[str, bool] | None = None,
) -> dict[str, bool]:
    """인자별 제어 가능 여부 (미입력 시 환경 키워드 자동 제외)."""
    out: dict[str, bool] = {}
    for name in factor_names:
        if controllability is not None and name in controllability:
            out[name] = bool(controllability[name])
        else:
            out[name] = not _is_environment_factor(name)
    return out


def _chart_type_for_factor(x_type: str, y_is_continuous: bool = True) -> str:
    if not y_is_continuous:
        if x_type == TYPE_CATEGORICAL:
            return "p 차트 (또는 np)"
        return "p 차트"
    if x_type == TYPE_CONTINUOUS:
        return "X-bar R 또는 I-MR"
    return "p / np / c / u (범주형 공정)"


def generate_spc_recommendations(
    matrix_df: pd.DataFrame,
    multiple_regression: dict[str, Any] | None = None,
    controllability: dict[str, bool] | None = None,
    structure: dict | None = None,
    max_ctp: int = 3,
) -> dict[str, Any]:
    """
    점수·순수 기여도·제어 가능성 기반 CTP 및 SPC 권고.
    """
    score_col = "score" if "score" in matrix_df.columns else None
    if score_col is None:
        return {"error": "매트릭스에 score 컬럼이 없습니다."}

    candidates = matrix_df[matrix_df[score_col] >= 3].copy()
    if candidates.empty:
        candidates = matrix_df[matrix_df[score_col] >= 1].head(max_ctp)
    if candidates.empty:
        return {
            "ctp_factors": [],
            "message": "유의한 X인자(점수≥1)가 없습니다.",
        }

    x_col_key = "x_column" if "x_column" in candidates.columns else "X 인자명"
    factor_names = candidates[x_col_key].tolist()
    ctrl = infer_controllability(factor_names, controllability)

    unique_contrib = (
        multiple_regression.get("unique_contributions", {})
        if multiple_regression
        else {}
    )

    def sort_key(row: pd.Series) -> tuple:
        name = row[x_col_key]
        contrib = unique_contrib.get(name, row.get("r_square", 0) or 0)
        return (0 if ctrl.get(name, True) else 1, -row[score_col], -contrib)

    ranked = candidates.copy()
    ranked["_sort"] = ranked.apply(sort_key, axis=1)
    ranked = ranked.sort_values("_sort").drop(columns=["_sort"])

    controllable = ranked[ranked[x_col_key].map(lambda n: ctrl.get(n, True))]
    ctp_rows = controllable.head(max_ctp)
    monitor_rows = ranked[~ranked.index.isin(ctp_rows.index)]

    x_types = (structure or {}).get("x_types", {})
    y_types = (structure or {}).get("y_types", {})
    y_col = (structure or {}).get("selected_y")
    y_continuous = True
    if y_col and y_types:
        from src.xy_matrix.constants import TYPE_CONTINUOUS
        y_continuous = y_types.get(y_col) == TYPE_CONTINUOUS

    ctp_list = []
    for _, row in ctp_rows.iterrows():
        name = row[x_col_key]
        xt = row.get("x_type", x_types.get(name, TYPE_CONTINUOUS))
        ctp_list.append({
            "factor": name,
            "x_type": xt,
            "score": int(row[score_col]),
            "symbol": row.get("symbol", ""),
            "unique_contribution": unique_contrib.get(name),
            "chart_recommendation": _chart_type_for_factor(xt, y_continuous),
            "controllable": True,
        })

    monitoring = []
    for _, row in monitor_rows.iterrows():
        name = row[x_col_key]
        if not ctrl.get(name, True) or _is_environment_factor(name):
            monitoring.append({
                "factor": name,
                "reason": "환경/제어 불가 인자 — 모니터링만 권장",
                "score": int(row[score_col]),
            })

    vif_warnings = []
    if multiple_regression:
        vif_warnings = multiple_regression.get("vif_warnings", [])

    return {
        "ctp_factors": ctp_list,
        "monitoring_factors": monitoring,
        "controllability": ctrl,
        "vif_warnings": vif_warnings,
        "summary": (
            f"CTP {len(ctp_list)}개 선정, 모니터링 {len(monitoring)}개"
            + ("; VIF>10 다중공선성 주의" if vif_warnings else "")
        ),
    }
