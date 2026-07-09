"""채취 표본 행 — 필터 후 원본 매칭 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.spc.sample_row_match import align_sampled_mask, build_sampled_row_mask
from src.spc.sampler import SampleSelector


def test_build_sampled_row_mask_uses_original_index():
    filtered = pd.DataFrame({
        "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        "lot": ["L1"] * 10,
    })
    selector = SampleSelector(filtered)
    sample_df, _ = selector.select(method="consecutive", subgroup_size=2, n_subgroups=2)
    mask = build_sampled_row_mask(filtered, sample_df)
    assert isinstance(mask, pd.Series)
    assert int(mask.sum()) == len(sample_df)
    assert "original_index" in sample_df.columns


def test_build_sampled_row_mask_returns_series():
    filtered = pd.DataFrame({"value": [1.0, 2.0, 3.0]})
    sample_df = filtered.iloc[[0, 2]].copy()
    sample_df["original_index"] = [0, 2]
    mask = build_sampled_row_mask(filtered, sample_df.reset_index(drop=True))
    assert isinstance(mask, pd.Series)
    assert list(mask) == [True, False, True]


def test_align_sampled_mask_from_ndarray():
    mask = align_sampled_mask(np.array([True, False, True]), 3)
    assert isinstance(mask, pd.Series)
    assert list(mask) == [True, False, True]


def test_build_sampled_row_mask_fallback_merge():
    filtered = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=5, freq="h"),
        "value": [1.1, 1.2, 1.3, 1.4, 1.5],
        "lot": ["A", "A", "B", "B", "C"],
    })
    sample_df = filtered.iloc[[1, 3]].copy().reset_index(drop=True)
    mask = build_sampled_row_mask(filtered, sample_df)
    assert isinstance(mask, pd.Series)
    assert list(mask) == [False, True, False, True, False]
