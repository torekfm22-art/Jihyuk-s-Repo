"""
상위 점수 X인자 대상 다중회귀 및 순수/공통 기여도, VIF.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

from src.xy_matrix.constants import TYPE_CATEGORICAL, TYPE_CONTINUOUS

logger = logging.getLogger(__name__)


def _build_design_matrix(
    df: pd.DataFrame,
    top_x_cols: list[str],
    x_types: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """범주형 더미 변환 후 설계 행렬."""
    X = df[top_x_cols].copy()
    dummy_map: dict[str, list[str]] = {}

    for col in top_x_cols:
        if x_types.get(col) == TYPE_CATEGORICAL:
            dummies = pd.get_dummies(X[col].astype(str), prefix=col, drop_first=True)
            dummy_map[col] = list(dummies.columns)
            X = X.drop(columns=[col]).join(dummies)
        else:
            X[col] = pd.to_numeric(X[col], errors="coerce")
            dummy_map[col] = [col]

    X = X.dropna()
    return X, dummy_map


def _columns_for_factor(factor: str, dummy_map: dict[str, list[str]], all_cols: list[str]) -> list[str]:
    if factor in dummy_map:
        return [c for c in all_cols if c in dummy_map[factor]]
    return [c for c in all_cols if c == factor or c.startswith(f"{factor}_")]


def run_multiple_regression(
    df: pd.DataFrame,
    y_col: str,
    top_x_cols: list[str],
    x_types: dict[str, str],
) -> dict[str, Any]:
    """
    9점·3점 인자 대상 OLS 다중회귀, 순수/공통 기여도, VIF.
    """
    if len(top_x_cols) < 2:
        raise ValueError("다중회귀에는 X인자 2개 이상이 필요합니다.")

    y = pd.to_numeric(df[y_col], errors="coerce")
    X, dummy_map = _build_design_matrix(df, top_x_cols, x_types)
    aligned = pd.concat([y, X], axis=1).dropna()
    if len(aligned) < len(top_x_cols) + 5:
        raise ValueError(f"다중회귀 표본 수({len(aligned)})가 부족합니다.")

    y_clean = aligned[y_col]
    X_clean = aligned.drop(columns=[y_col])
    x_cols = list(X_clean.columns)

    X_const = sm.add_constant(X_clean, has_constant="add")
    model = sm.OLS(y_clean, X_const).fit()

    unique_contributions: dict[str, float] = {}
    for factor in top_x_cols:
        keep = [
            c for c in x_cols
            if c not in _columns_for_factor(factor, dummy_map, x_cols)
        ]
        if not keep:
            unique_contributions[factor] = float(model.rsquared)
            continue
        reduced = sm.add_constant(X_clean[keep], has_constant="add")
        reduced_model = sm.OLS(y_clean, reduced).fit()
        unique_contributions[factor] = max(0.0, float(model.rsquared - reduced_model.rsquared))

    total_unique = sum(unique_contributions.values())
    shared = max(0.0, float(model.rsquared - total_unique))

    vif_data: dict[str, float] = {}
    x_values = X_clean.values.astype(float)
    for i, col in enumerate(x_cols):
        try:
            vif_data[col] = float(variance_inflation_factor(x_values, i))
        except Exception:
            vif_data[col] = float("nan")

    vif_warnings = [c for c, v in vif_data.items() if v > 10 and not np.isnan(v)]

    coefs = {}
    for name in model.params.index:
        if name == "const":
            continue
        coefs[name] = {
            "coefficient": float(model.params[name]),
            "p_value": float(model.pvalues[name]),
        }

    contrib_pct = {
        k: (v / model.rsquared * 100) if model.rsquared > 0 else 0.0
        for k, v in unique_contributions.items()
    }

    return {
        "multiple_r_square": float(model.rsquared),
        "adjusted_r_square": float(model.rsquared_adj),
        "f_value": float(model.fvalue) if model.fvalue is not None else np.nan,
        "p_value": float(model.f_pvalue) if model.f_pvalue is not None else np.nan,
        "unique_contributions": unique_contributions,
        "unique_contribution_pct": contrib_pct,
        "shared_contribution": shared,
        "shared_contribution_pct": (
            shared / model.rsquared * 100 if model.rsquared > 0 else 0.0
        ),
        "coefficients": coefs,
        "vif": vif_data,
        "vif_warnings": vif_warnings,
        "y_column": y_col,
        "x_factors": top_x_cols,
    }
