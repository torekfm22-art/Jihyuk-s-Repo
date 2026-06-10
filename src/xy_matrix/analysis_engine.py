"""
X-Y 유형 조합별 통계 분석 및 1-3-9 점수 산출.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, f_oneway, linregress

from src.xy_matrix.constants import (
    DEFAULT_SCORE_THRESHOLDS,
    P_VALUE_ALPHA,
    TYPE_CATEGORICAL,
    TYPE_CONTINUOUS,
    TYPE_COUNT,
)

logger = logging.getLogger(__name__)


def select_analysis_method(x_type: str, y_type: str) -> str:
    """X-Y 유형 조합 → 분석 기법 코드."""
    if y_type == "분석불가":
        raise ValueError("Y인자 유형이 분석 불가입니다.")

    if x_type == TYPE_CONTINUOUS and y_type == TYPE_CONTINUOUS:
        return "linear_regression"
    if x_type == TYPE_CATEGORICAL and y_type == TYPE_CONTINUOUS:
        return "anova"
    if x_type == TYPE_CONTINUOUS and y_type == TYPE_COUNT:
        return "logistic_regression"
    if x_type == TYPE_CATEGORICAL and y_type == TYPE_COUNT:
        return "chi_square"

    raise ValueError(f"지원하지 않는 X-Y 조합: X={x_type}, Y={y_type}")


def _method_label(method: str) -> str:
    return {
        "linear_regression": "선형회귀분석",
        "anova": "ANOVA",
        "logistic_regression": "로지스틱 회귀분석",
        "chi_square": "카이제곱 검정",
    }.get(method, method)


def _prepare_xy(
    df: pd.DataFrame, y_col: str, x_col: str
) -> tuple[pd.Series, pd.Series]:
    sub = df[[y_col, x_col]].dropna()
    if len(sub) < 10:
        raise ValueError(
            f"'{x_col}' vs '{y_col}': 유효 표본 수({len(sub)})가 부족합니다 (최소 10)."
        )
    return sub[y_col], sub[x_col]


def _encode_count_y(y: pd.Series) -> tuple[np.ndarray, bool]:
    """계수형 Y → 이진(2수준) 또는 다범주 인코딩."""
    uniq = y.dropna().unique()
    if len(uniq) < 2:
        raise ValueError("Y인자에 2개 이상의 수준이 필요합니다.")
    if len(uniq) == 2:
        mapping = {uniq[0]: 0, uniq[1]: 1}
        return y.map(mapping).to_numpy(dtype=float), True
    codes, _ = pd.factorize(y)
    if len(uniq) > 2:
        logger.info("다범주 Y(%d수준): 로지스틱/카이제곱은 0/1 대표코드 사용.", len(uniq))
    return codes.astype(float), False


def run_statistical_analysis(
    df: pd.DataFrame,
    y_col: str,
    x_col: str,
    method: str,
) -> dict[str, Any]:
    """선택된 기법으로 통계 분석 실행."""
    y, x = _prepare_xy(df, y_col, x_col)
    result: dict[str, Any] = {"method": _method_label(method), "method_code": method}

    if method == "linear_regression":
        x_num = pd.to_numeric(x, errors="coerce")
        y_num = pd.to_numeric(y, errors="coerce")
        mask = x_num.notna() & y_num.notna()
        x_arr, y_arr = x_num[mask].to_numpy(), y_num[mask].to_numpy()
        if len(x_arr) < 10:
            raise ValueError("선형회귀: 유효 숫자 쌍이 부족합니다.")
        slope, intercept, r_value, p_value, std_err = linregress(x_arr, y_arr)
        result.update({
            "r_square": float(r_value ** 2),
            "p_value": float(p_value),
            "coefficient": float(slope),
            "intercept": float(intercept),
            "correlation": float(r_value),
            "std_err": float(std_err),
        })

    elif method == "anova":
        y_num = pd.to_numeric(y, errors="coerce")
        groups = [y_num[x == cat].dropna().to_numpy() for cat in x.dropna().unique()]
        groups = [g for g in groups if len(g) >= 2]
        if len(groups) < 2:
            raise ValueError("ANOVA: 그룹이 2개 미만이거나 표본이 부족합니다.")
        f_val, p_val = f_oneway(*groups)
        y_clean = y_num.dropna()
        ss_between = sum(len(g) * (g.mean() - y_clean.mean()) ** 2 for g in groups)
        ss_total = ((y_clean - y_clean.mean()) ** 2).sum()
        eta_sq = ss_between / ss_total if ss_total > 0 else 0.0
        result.update({
            "r_square": float(eta_sq),
            "p_value": float(p_val),
            "f_value": float(f_val),
            "effect_size": float(eta_sq),
        })

    elif method == "logistic_regression":
        import statsmodels.api as sm
        from sklearn.metrics import roc_auc_score

        y_bin, is_binary = _encode_count_y(y)
        x_num = pd.to_numeric(x, errors="coerce").to_numpy()
        mask = ~np.isnan(x_num) & ~np.isnan(y_bin)
        x_arr, y_arr = x_num[mask], y_bin[mask]
        if len(x_arr) < 10:
            raise ValueError("로지스틱 회귀: 유효 표본이 부족합니다.")
        X = sm.add_constant(x_arr)
        try:
            model = sm.Logit(y_arr, X).fit(disp=0)
        except Exception as exc:
            raise ValueError(f"로지스틱 회귀 실패: {exc}") from exc
        pseudo_r2 = float(model.prsquared)
        p_val = float(model.pvalues[1]) if len(model.pvalues) > 1 else np.nan
        odds = float(np.exp(model.params[1])) if len(model.params) > 1 else np.nan
        auc = np.nan
        if is_binary and len(np.unique(y_arr)) == 2:
            try:
                auc = float(roc_auc_score(y_arr, model.predict(X)))
            except Exception:
                pass
        result.update({
            "r_square": pseudo_r2,
            "pseudo_r_square": pseudo_r2,
            "p_value": p_val,
            "odds_ratio": odds,
            "auc": auc,
            "coefficient": float(model.params[1]) if len(model.params) > 1 else np.nan,
        })

    elif method == "chi_square":
        y_enc, _ = _encode_count_y(y)
        tab = pd.crosstab(x.astype(str), pd.Series(y_enc).astype(str))
        if tab.shape[0] < 2 or tab.shape[1] < 2:
            raise ValueError("카이제곱: 분할표가 2×2 이상이어야 합니다.")
        chi2, p_val, dof, expected = chi2_contingency(tab)
        n = tab.sum().sum()
        min_dim = min(tab.shape) - 1
        cramers_v = np.sqrt(chi2 / (n * min_dim)) if n > 0 and min_dim > 0 else 0.0
        result.update({
            "chi_square": float(chi2),
            "p_value": float(p_val),
            "cramers_v": float(cramers_v),
            "r_square": float(cramers_v ** 2),
            "effect_size": float(cramers_v),
        })
    else:
        raise ValueError(f"알 수 없는 분석 기법: {method}")

    return result


def calculate_score(
    p_value: float,
    r_square: float,
    thresholds: dict | None = None,
) -> tuple[int, str, str]:
    """P-value·효과크기(R² 등) 기반 1-3-9 점수."""
    th = {**DEFAULT_SCORE_THRESHOLDS, **(thresholds or {})}
    strong = th.get("9점", th.get("strong", 0.7))
    moderate = th.get("3점", th.get("moderate", 0.4))

    if p_value is None or (isinstance(p_value, float) and np.isnan(p_value)):
        return 0, "✗", "P-value 계산 불가"
    if p_value >= P_VALUE_ALPHA:
        return 0, "✗", "통계적 유의성 없음"
    if r_square >= strong:
        return 9, "◎", "강한 상관관계"
    if r_square >= moderate:
        return 3, "○", "보통 상관관계"
    return 1, "△", "약한 상관관계"
