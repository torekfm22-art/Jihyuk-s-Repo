"""X-Y 상관 매트릭스 계산."""
from __future__ import annotations

import pandas as pd


def build_correlation_matrix(
    wide_df: pd.DataFrame,
    y_column: str,
    x_columns: list[str] | None = None,
    *,
    method: str = "pearson",
    min_valid_rows: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """
    wide 테이블에서 Y와 X들의 상관 매트릭스 생성.

    Returns:
        full_matrix: Y+X 전체 상관
        y_vs_x: Y 대 X 1행 요약
        valid_row_count: 숫자 변환 후 유효 행 수
    """
    meta_cols = {"_anchor_index", "_anchor_time"}
    if x_columns is None:
        x_columns = [c for c in wide_df.columns if c not in meta_cols and c != y_column]

    cols = [y_column] + [c for c in x_columns if c in wide_df.columns]
    numeric = wide_df[cols].apply(pd.to_numeric, errors="coerce")
    valid = numeric.dropna(how="any")
    if len(valid) < min_valid_rows:
        empty = pd.DataFrame()
        return empty, empty, len(valid)

    full_matrix = valid.corr(method=method)
    y_vs_x = full_matrix.loc[[y_column], [c for c in cols if c != y_column]]
    return full_matrix, y_vs_x, len(valid)
