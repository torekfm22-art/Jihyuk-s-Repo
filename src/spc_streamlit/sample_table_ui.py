"""데이터 분석 — 원본 테이블 채취 행 표시."""
from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
import streamlit as st

from src.spc import sample_row_match as _sample_row_match_module
from src.spc.pipeline import SpcPipelineResult

importlib.reload(_sample_row_match_module)
build_sampled_row_mask = _sample_row_match_module.build_sampled_row_mask

_SAMPLE_ROW_COLOR = "background-color: #ffc0cb"


def _align_sampled_mask(mask, length: int) -> pd.Series:
    """표시용 0..n-1 길이 bool Series (ndarray·Series 모두 허용)."""
    if isinstance(mask, pd.Series):
        values = mask.to_numpy(dtype=bool, copy=False)
    else:
        values = np.asarray(mask, dtype=bool)
    if len(values) != length:
        aligned = np.zeros(length, dtype=bool)
        n = min(length, len(values))
        if n:
            aligned[:n] = values[:n]
        values = aligned
    return pd.Series(values)


def style_sampled_rows(display_df: pd.DataFrame, sampled_mask: pd.Series) -> pd.io.formats.style.Styler:
    mask = _align_sampled_mask(sampled_mask, len(display_df))

    def _highlight(row: pd.Series):
        if row.name < len(mask) and bool(mask.iloc[row.name]):
            return [_SAMPLE_ROW_COLOR] * len(row)
        return [""] * len(row)

    return display_df.style.apply(_highlight, axis=1)


def render_filtered_data_with_sample_highlight(active: SpcPipelineResult) -> None:
    """원본 데이터(필터 후) — 채취된 행 분홍 표시."""
    filtered = active.filtered_df
    sample = active.sample_df

    if filtered is None or filtered.empty:
        st.info("원본 데이터 테이블이 없습니다.")
        return

    display_df = filtered.reset_index(drop=True)
    sampled_mask = _align_sampled_mask(
        build_sampled_row_mask(filtered, sample),
        len(display_df),
    )
    n_sampled = int(sampled_mask.sum())

    st.caption(
        f"총 **{len(filtered)}**행 (필터 적용 후) · "
        f"분홍 **{n_sampled}**행 = 채취 표본에 포함된 데이터"
    )
    if n_sampled == 0 and sample is not None and not sample.empty:
        st.warning("채취 표본과 원본 행 매칭에 실패했습니다. 채취 표본 탭에서 내용을 확인하세요.")

    st.dataframe(
        style_sampled_rows(display_df, sampled_mask),
        use_container_width=True,
        height=400,
    )
