"""SampleSelector — I-MR / subgroup 채취 테스트."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src.spc.sampler import (
    VIRTUAL_BOUNDARY_SHIFT,
    SampleSelector,
    list_virtual_boundary_options,
)


def _make_timed_data(
    n_lots: int = 30,
    per_lot: int = 8,
    minutes_step: int = 15,
) -> pd.DataFrame:
    rows: list[dict] = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    idx = 0
    for lot_i in range(n_lots):
        for j in range(per_lot):
            rows.append({
                "value": 10.0 + lot_i * 0.01 + j * 0.001,
                "timestamp": base + timedelta(minutes=idx * minutes_step),
                "lot": f"LOT-{lot_i:03d}",
                "shift": "주간" if (base + timedelta(minutes=idx * minutes_step)).hour < 20 else "야간",
            })
            idx += 1
    return pd.DataFrame(rows)


def test_imr_lot_unit_one_per_lot():
    df = _make_timed_data(n_lots=30, per_lot=8)
    selector = SampleSelector(df)
    sample_df = selector.select_rational_individuals(n_points=25, unit="lot")
    assert len(sample_df) == 25
    assert sample_df["lot"].nunique() == 25
    assert sample_df["sampling_strategy"].iloc[0] == "imr_rational_lot"


def test_imr_hour_unit():
    df = _make_timed_data(n_lots=5, per_lot=40, minutes_step=10)
    selector = SampleSelector(df)
    sample_df = selector.select_rational_individuals(n_points=25, unit="hour")
    assert len(sample_df) <= 25
    assert sample_df["sampling_strategy"].iloc[0] == "imr_rational_hour"


def test_imr_cycle_unit_stride():
    df = _make_timed_data(n_lots=3, per_lot=50, minutes_step=1)
    selector = SampleSelector(df)
    sample_df = selector.select_rational_individuals(n_points=25, unit="cycle", cycle_stride=5)
    assert len(sample_df) >= 2
    assert sample_df["sampling_strategy"].iloc[0] == "imr_rational_cycle"


def test_imr_hour_one_per_hour_single_characteristic():
    """단일 검사항목 — 시간당 1대표점."""
    ts = datetime(2026, 6, 2, 9, 26, 11)
    rows = []
    for i in range(5):
        rows.append({
            "value": 0.01 * i,
            "timestamp": ts + timedelta(minutes=i * 3),
            "lot": f"LOT-{i}",
            "line": "ST01",
            "machine": "ST01-140-01",
            "process": "터미널 높이 검사",
            "characteristic": "높이 측정 데이터#4",
        })
    rows.append({
        "value": 0.0,
        "timestamp": datetime(2026, 6, 2, 10, 21, 19),
        "lot": "LOT-B",
        "line": "ST01",
        "machine": "ST01-140-01",
        "process": "터미널 높이 검사",
        "characteristic": "높이 측정 데이터#4",
    })
    selector = SampleSelector(pd.DataFrame(rows))
    sample_df = selector.select_rational_individuals(n_points=25, unit="hour")
    assert len(sample_df) == 2


def test_imr_hour_one_per_hour_across_lots():
    """동일 시간대 여러 LOT → 1시간 1대표점 (LOT별 분리 금지)."""
    rows = []
    for i in range(15):
        rows.append({
            "value": -0.1 + i * 0.01,
            "timestamp": datetime(2026, 6, 2, 11, 40) + timedelta(minutes=i),
            "lot": f"LOT-{i:03d}",
            "line": "ST01",
            "machine": "ST01-140-01",
            "process": "터미널 높이 검사",
            "characteristic": "높이 측정 데이터#4",
        })
    for i in range(5):
        rows.append({
            "value": 0.05,
            "timestamp": datetime(2026, 6, 2, 12, 2) + timedelta(minutes=i * 2),
            "lot": f"LOT-B{i}",
            "line": "ST01",
            "machine": "ST01-140-01",
            "process": "터미널 높이 검사",
            "characteristic": "높이 측정 데이터#4",
        })
    selector = SampleSelector(pd.DataFrame(rows))
    sample_df = selector.select_rational_individuals(n_points=25, unit="hour")
    assert sample_df["sampling_strategy"].iloc[0] == "imr_rational_hour"
    assert len(sample_df) == 2
    buckets = sorted(sample_df["sampling_hour_bucket"].astype(str).unique())
    assert "2026-06-02 11:00:00" in buckets[0] or "2026-06-02 11:00:00" in buckets


def test_imr_hour_inferred_when_date_only():
    df = _make_timed_data(n_lots=3, per_lot=60, minutes_step=1)
    df["timestamp"] = df["timestamp"].dt.normalize()
    selector = SampleSelector(df)
    sample_df = selector.select_rational_individuals(n_points=25, unit="hour")
    assert sample_df["sampling_strategy"].iloc[0] == "imr_rational_hour"
    assert "sampling_hour_bucket" in sample_df.columns
    assert sample_df["sampling_hour_bucket"].nunique() >= 3


def test_imr_auto_detects_lot():
    df = _make_timed_data(n_lots=30, per_lot=6)
    selector = SampleSelector(df)
    sample_df = selector.select_rational_individuals(n_points=25, unit="auto")
    assert sample_df["imr_sampling_unit"].iloc[0] == "lot"


def test_xbar_subgroup_sampling_unchanged():
    df = _make_timed_data(n_lots=30, per_lot=5)
    selector = SampleSelector(df)
    sample_df, sg_size = selector.select(method="consecutive", subgroup_size=5, n_subgroups=25)
    assert sg_size == 5
    assert len(sample_df) == 125
    counts = sample_df.groupby("subgroup_id").size()
    assert (counts == 5).all()


def test_xbar_sliding_window_more_candidates():
    """블록 7행 → stride 1 슬라이딩으로 연속 5개 후보 3개 이상."""
    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    for j in range(7):
        rows.append({
            "value": 10.0 + j * 0.01,
            "timestamp": base + timedelta(minutes=j * 5),
            "lot": "LOT-001",
            "shift": "주간",
        })
    selector = SampleSelector(pd.DataFrame(rows))
    prep = selector._prepare_for_sampling()
    blocks = selector._split_blocks(prep)
    cands = selector._collect_candidates(blocks, 5)
    assert len(cands) == 3
    assert all(len(c["chunk"]) == 5 for c in cands)


def test_xbar_fallback_when_block_candidates_insufficient():
    """블록 후보가 목표 군 수보다 적으면 가능한 군만 사용 (순번 랜덤 대체 금지)."""
    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    for lot_i in range(4):
        for j in range(5):
            rows.append({
                "value": 10.0 + lot_i * 0.1 + j * 0.01,
                "timestamp": base + timedelta(hours=lot_i, minutes=j * 10),
                "lot": f"LOT-{lot_i:03d}",
                "shift": "주간",
            })
    selector = SampleSelector(pd.DataFrame(rows))
    sample_df, sg_size = selector.select(method="consecutive", subgroup_size=5, n_subgroups=25)
    assert sg_size == 5
    counts = sample_df.groupby("subgroup_id").size()
    assert (counts == 5).all()
    assert len(counts) == 16  # 20행 → 슬라이딩 후보 16개
    assert sample_df["sampling_strategy"].iloc[0].startswith("boundary_block")


def test_manual_lot_boundary_prevents_mixing():
    """직접 지정 + LOT: subgroup 내 LOT 혼합 금지 (LOT당 2행 이상일 때)."""
    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    for lot_i in range(4):
        for j in range(5):
            rows.append({
                "value": 10.0 + lot_i * 0.1 + j * 0.01,
                "timestamp": base + timedelta(minutes=lot_i * 10 + j),
                "lot": f"LOT-{lot_i:03d}",
                "shift": "주간",
            })
    selector = SampleSelector(
        pd.DataFrame(rows),
        subgroup_boundary_keys=["date", "shift", "lot"],
    )
    prep = selector._prepare_for_sampling()
    blocks = selector._split_blocks(prep)
    cands = selector._collect_candidates(blocks, 5)
    assert len(cands) == 4
    for c in cands:
        assert c["chunk"]["lot"].nunique() == 1


def test_manual_machine_only_no_date_balanced_pick():
    """설비 컬럼만 선택 시 date_block이 아님."""
    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    for day in range(5):
        for j in range(10):
            rows.append({
                "value": 10.0 + day * 0.01 + j * 0.001,
                "timestamp": base + timedelta(days=day, minutes=j * 5),
                "lot": f"LOT-{day}-{j}",
                "shift": "주간",
                "machine": "ST01-094-02",
            })
    selector = SampleSelector(
        pd.DataFrame(rows),
        subgroup_boundary_columns=["machine"],
    )
    sample_df, _ = selector.select(method="consecutive", subgroup_size=5, n_subgroups=10)
    strat = sample_df["sampling_strategy"].iloc[0]
    assert strat == "boundary_block:machine"
    assert sample_df["sampling_boundary"].iloc[0] == "machine"
    assert "date_block" not in strat


def test_manual_date_still_uses_date_balanced_pick():
    """날짜 포함 시 일자 분산 채취 유지."""
    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    for day in range(10):
        for j in range(8):
            rows.append({
                "value": 10.0 + j * 0.01,
                "timestamp": base + timedelta(days=day, minutes=j * 5),
                "lot": f"LOT-{day}",
                "shift": "주간",
                "machine": "ST01-094-02",
            })
    selector = SampleSelector(
        pd.DataFrame(rows),
        subgroup_boundary_keys=["date", "shift", "machine"],
    )
    sample_df, _ = selector.select(method="consecutive", subgroup_size=5, n_subgroups=15)
    assert "date" in sample_df["sampling_strategy"].iloc[0]
    dates = pd.to_datetime(sample_df["timestamp"]).dt.date
    assert dates.nunique() >= 5


def test_virtual_shift_boundary_without_shift_column():
    """교대 컬럼 없이 가상 교대 선택 — 측정일시로 주간/야간 분리."""
    rows = []
    base_day = datetime(2026, 1, 1, 8, 0, 0)
    base_night = datetime(2026, 1, 1, 22, 0, 0)
    for i in range(20):
        rows.append({
            "value": 10.0 + i * 0.01,
            "timestamp": base_day + timedelta(minutes=i * 30),
            "lot": f"LOT-D-{i}",
            "machine": "M1",
        })
    for i in range(20):
        rows.append({
            "value": 20.0 + i * 0.01,
            "timestamp": base_night + timedelta(minutes=i * 30),
            "lot": f"LOT-N-{i}",
            "machine": "M1",
        })
    df = pd.DataFrame(rows)
    assert "shift" not in df.columns
    assert list_virtual_boundary_options(df)

    selector = SampleSelector(
        df,
        subgroup_boundary_columns=[VIRTUAL_BOUNDARY_SHIFT, "machine"],
    )
    prep = selector._prepare_for_sampling()
    assert prep["_block_shift"].isin(["주간", "야간"]).all()
    blocks = selector._split_blocks(prep)
    block_keys = {str(k) for k, _ in blocks}
    assert any("주간" in k for k in block_keys)
    assert any("야간" in k for k in block_keys)

    sample_df, sg_size = selector.select(method="consecutive", subgroup_size=5, n_subgroups=4)
    assert sg_size == 5
    assert "교대 (시간대 자동)" in sample_df["sampling_strategy"].iloc[0]


def test_xbar_one_row_per_lot_uses_shift_block():
    """LOT당 1행(터미널 높이 #6) — 일자·교대 블록 내 연속 5대로 군 구성."""
    rows = []
    base = datetime(2026, 5, 7, 8, 43, 0)
    for i in range(120):
        rows.append({
            "value": -0.1 + (i % 10) * 0.01,
            "timestamp": base + timedelta(minutes=i * 2),
            "lot": f"365301XFB0,SFZOT{i:06d}",
            "line": "ST01",
            "machine": "ST01-140-01",
            "process": "터미널 높이 검사",
            "characteristic": "높이 측정 데이터#6",
        })
    selector = SampleSelector(pd.DataFrame(rows))
    sample_df, sg_size = selector.select(method="consecutive", subgroup_size=5, n_subgroups=25)
    assert sg_size == 5
    assert sample_df["sampling_strategy"].iloc[0].startswith("boundary_block")
    counts = sample_df.groupby("subgroup_id").size()
    assert (counts == 5).all()
    assert len(counts) == 25
    for _, g in sample_df.groupby("subgroup_id", sort=True):
        g = g.sort_values("timestamp")
        ts = pd.to_datetime(g["timestamp"])
        assert ts.is_monotonic_increasing
        assert g["lot"].nunique() == 5


def test_subgroups_ordered_by_measure_time_boundary():
    """검사시간(measure_time) 기준 분리 — subgroup_id가 시간순."""
    from src.spc.data_extractor import _normalize_columns

    rows = []
    base = datetime(2026, 1, 1, 8, 0, 0)
    for day in range(10):
        for j in range(8):
            rows.append({
                "value": 10.0 + j * 0.01,
                "검사시간": base + timedelta(days=day, minutes=j * 5),
                "machine": "M1",
            })
    df = _normalize_columns(pd.DataFrame(rows))
    selector = SampleSelector(df, subgroup_boundary_columns=["measure_time"])
    sample_df, _ = selector.select(method="consecutive", subgroup_size=5, n_subgroups=10, random_state=42)
    sg_starts = sample_df.groupby("subgroup_id")["measure_time"].min()
    assert sg_starts.is_monotonic_increasing, sg_starts.to_dict()
