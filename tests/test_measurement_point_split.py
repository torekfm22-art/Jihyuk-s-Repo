"""측정 포인트(네트 갯수 등) 자동 분리."""
from __future__ import annotations

import pandas as pd

from src.spc.characteristic_split import (
    COMPOSITE_SPLIT_COLUMN,
    build_manual_split_options,
    build_measurement_point_preview,
    detect_measurement_point_column,
    format_split_label,
    list_measurement_point_column_candidates,
    list_split_values,
    recommend_composite_columns,
    resolve_split_plan,
    select_auto_measurement_point_values,
    summarize_composite_split,
    summarize_measurement_points,
)
from src.spc.data_extractor import (
    _ensure_measurement_point_column,
    _normalize_columns,
    _score_measurement_point_column,
)

COLS = [
    "S/NO", "품번", "공정", "공정명", "설비 ID", "작업", "작업명",
    "네트 갯수", "값 갯수", "단위", "하한값", "상한값", "값",
    "트랜잭션 시간",
]


def test_net_count_column_detected_as_measurement_point():
    rows = []
    for pt in (1, 2, 3):
        for i in range(5):
            row = {c: 1.0 for c in COLS}
            row["네트 갯수"] = pt
            row["값"] = 10.0 + pt + i * 0.01
            row["트랜잭션 시간"] = f"2026-06-01 10:{i+pt:02d}:00"
            rows.append(row)
    df = pd.DataFrame(rows)
    norm = _ensure_measurement_point_column(_normalize_columns(df))
    assert "measurement_point" in norm.columns
    col = detect_measurement_point_column(norm)
    assert col == "measurement_point"
    assert list_split_values(norm, col) == ["1", "2", "3"]


def test_format_split_label_point():
    assert format_split_label("2", "measurement_point") == "측정 포인트 2"
    assert format_split_label("EQ-01", "machine") == "설비 EQ-01"


def test_equipment_id_detected_as_measurement_point_column():
    rows = []
    for eq in ("EQ-01", "EQ-02", "EQ-03"):
        for i in range(5):
            row = {c: 1.0 for c in COLS}
            row["설비 ID"] = eq
            row["값"] = 10.0 + i
            row["트랜잭션 시간"] = f"2026-06-01 10:0{i}:00"
            rows.append(row)
    df = _normalize_columns(pd.DataFrame(rows))
    cands = list_measurement_point_column_candidates(df)
    assert cands
    assert cands[0][0] == "machine"
    prev = build_measurement_point_preview(df, column_display_names={"machine": "설비 ID"})
    assert prev["recommended_column"] == "machine"
    assert prev["recommended_display_column"] == "설비 ID"
    assert len(prev["candidates"][0]["summary"]) == 3


def test_point_picker_option_map_shows_full_labels():
    from src.spc.characteristic_split import format_point_picker_option, point_picker_option_map

    summary = [
        {"point_id": "EQ-01", "row_count": 10},
        {"point_id": "EQ-02", "row_count": 8},
    ]
    opts = point_picker_option_map(summary, "machine")
    assert all("설비" in k for k in opts)
    assert "EQ-01" in format_point_picker_option("EQ-01", "machine", row_count=10)


def test_summarize_measurement_points():
    df = pd.DataFrame({"measurement_point": ["1", "1", "2"], "value": [1, 2, 3]})
    summary = summarize_measurement_points(df, "measurement_point")
    assert len(summary) == 2
    assert summary[0]["row_count"] == 2


def test_net_count_preferred_over_serial_column():
    """순번(고유값 많음)보다 네트 갯수 열이 측정 포인트로 추천."""
    rows = []
    for pt in (1, 2, 3, 4):
        for i in range(10):
            rows.append({
                "네트 갯수": pt,
                "값": 10.0 + pt,
                "순번": pt * 100 + i,
                "트랜잭션 시간": f"2026-06-01 10:{i:02d}:00",
            })
    df = _normalize_columns(pd.DataFrame(rows))
    cands = list_measurement_point_column_candidates(df)
    assert cands
    assert cands[0][0] in ("measurement_point", "네트 갯수")


def test_auto_select_caps_measurement_points():
    rows = []
    for pt in range(1, 21):
        for i in range(10):
            rows.append({
                "네트 갯수": pt,
                "값": 10.0 + pt,
                "트랜잭션 시간": f"2026-06-01 {pt:02d}:{i:02d}:00",
            })
    df = _normalize_columns(pd.DataFrame(rows))
    norm = _ensure_measurement_point_column(df)
    col = detect_measurement_point_column(norm)
    assert col == "measurement_point"
    assert len(list_split_values(norm, col)) == 20
    auto = select_auto_measurement_point_values(norm, col, max_points=8)
    assert len(auto) == 8
    _, col2, vals = resolve_split_plan(
        norm, measurement_point_mode="auto", max_auto_measurement_points=8,
    )
    assert col2 == "measurement_point"
    assert len(vals) == 8


def test_manual_split_options_lists_all_values_without_scoring():
    rows = []
    for eq in ("EQ-01", "EQ-02", "EQ-03"):
        for i in range(2):
            rows.append({
                "설비 ID": eq,
                "네트 갯수": 1,
                "값": 10.0 + i,
                "트랜잭션 시간": f"2026-06-01 10:0{i}:00",
            })
    df = _normalize_columns(pd.DataFrame(rows))
    opts = build_manual_split_options(df, column_display_names={"machine": "설비 ID"})
    machine_opt = next(o for o in opts if o["column"] == "machine")
    assert len(machine_opt["summary"]) == 3
    assert {s["point_id"] for s in machine_opt["summary"]} == {"EQ-01", "EQ-02", "EQ-03"}


def test_manual_preview_includes_all_point_values():
    rows = []
    for pt in range(1, 25):
        for i in range(3):
            rows.append({
                "네트 갯수": pt,
                "값": 10.0 + pt,
                "트랜잭션 시간": f"2026-06-01 {pt:02d}:{i:02d}:00",
            })
    df = _normalize_columns(pd.DataFrame(rows))
    prev = build_measurement_point_preview(df)
    col_cand = next(c for c in prev["candidates"] if c["column"] in ("measurement_point", "네트 갯수"))
    assert len(col_cand["summary"]) == 24
    assert len(col_cand["point_ids"]) == 24


def test_more_than_30_levels_available_for_manual_preview():
    rows = []
    for pt in range(1, 36):
        rows.append({
            "네트 갯수": pt,
            "값": 10.0 + pt,
            "트랜잭션 시간": f"2026-06-01 10:{pt:02d}:00",
        })
    df = _normalize_columns(pd.DataFrame(rows))
    prev = build_measurement_point_preview(df)
    assert prev["recommended_column"]
    assert len(prev["candidates"][0]["summary"]) == 35


def test_build_measurement_point_preview_lists_candidates():
    df = pd.DataFrame({
        "measurement_point": ["1", "1", "2", "3"],
        "value": [1.0, 2.0, 3.0, 4.0],
    })
    prev = build_measurement_point_preview(df)
    assert prev["recommended_column"] == "measurement_point"
    assert len(prev["candidates"]) >= 1
    assert len(prev["summary"]) == 3


def test_resolve_split_manual_points():
    df = pd.DataFrame({
        "measurement_point": ["1", "1", "2", "2"],
        "value": [1.0, 2.0, 3.0, 4.0],
    })
    _, col, vals = resolve_split_plan(
        df, measurement_point_mode="manual", measurement_point_values=["2"],
    )
    assert col == "measurement_point"
    assert vals == ["2"]


def test_composite_split_item_and_machine():
    rows = []
    for eq in ("EQ-01", "EQ-02"):
        for item in ("A", "B"):
            for i in range(3):
                rows.append({
                    "설비 ID": eq,
                    "품번": item,
                    "값": 10.0 + i,
                    "트랜잭션 시간": f"2026-06-01 10:0{i}:00",
                })
    df = _normalize_columns(pd.DataFrame(rows))
    summary = summarize_composite_split(df, ["item", "machine"])
    assert len(summary) == 4
    ids = {s["point_id"] for s in summary}
    assert "A · EQ-01" in ids or "EQ-01 · A" in ids

    _, col, vals = resolve_split_plan(
        df,
        measurement_point_mode="manual",
        measurement_point_columns=["item", "machine"],
        measurement_point_values=["A · EQ-01"],
    )
    assert col == COMPOSITE_SPLIT_COLUMN
    assert vals == ["A · EQ-01"]


def test_composite_split_three_columns():
    rows = []
    for eq in ("EQ-01", "EQ-02"):
        for item in ("A", "B"):
            for pt in (1, 2):
                for i in range(2):
                    rows.append({
                        "설비 ID": eq,
                        "품번": item,
                        "네트 갯수": pt,
                        "값": 10.0 + pt + i * 0.1,
                        "트랜잭션 시간": f"2026-06-01 10:0{i}:00",
                    })
    df = _normalize_columns(pd.DataFrame(rows))
    summary = summarize_composite_split(df, ["machine", "item", "measurement_point"])
    assert len(summary) == 8
    ids = {s["point_id"] for s in summary}
    assert any("EQ-01" in pid and "A" in pid and "1" in pid for pid in ids)

    rec = recommend_composite_columns(
        [{"column": "machine"}, {"column": "item"}, {"column": "measurement_point"}],
        n_columns=3,
    )
    assert rec == ["machine", "item", "measurement_point"]

    _, col, vals = resolve_split_plan(
        df,
        measurement_point_mode="manual",
        measurement_point_columns=["machine", "item", "measurement_point"],
        measurement_point_values=[next(iter(ids))],
    )
    assert col == COMPOSITE_SPLIT_COLUMN
    assert len(vals) == 1


def test_composite_split_five_columns():
    rows = []
    for eq in ("EQ-01",):
        for item in ("A",):
            for pt in (1,):
                for shift in ("주간", "야간"):
                    for lot in ("L01", "L02"):
                        for i in range(2):
                            rows.append({
                                "설비 ID": eq,
                                "품번": item,
                                "네트 갯수": pt,
                                "교대": shift,
                                "LOT": lot,
                                "값": 10.0 + i,
                                "트랜잭션 시간": f"2026-06-01 10:0{i}:00",
                            })
    df = _normalize_columns(pd.DataFrame(rows))
    cols = ["machine", "item", "measurement_point", "shift", "lot"]
    summary = summarize_composite_split(df, cols)
    assert len(summary) == 4

    rec = recommend_composite_columns(
        [{"column": c} for c in cols],
        n_columns=5,
    )
    assert rec == cols

    _, col, vals = resolve_split_plan(
        df,
        measurement_point_mode="manual",
        measurement_point_columns=cols,
        measurement_point_values=[str(summary[0]["point_id"])],
    )
    assert col == COMPOSITE_SPLIT_COLUMN
    assert len(vals) == 1
