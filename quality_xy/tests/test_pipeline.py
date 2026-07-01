"""키 탐지·시간 정렬·상관 분석 테스트."""
from __future__ import annotations

from quality_xy.correlation import build_correlation_matrix
from quality_xy.graph_linker import DatasetGraph
from quality_xy.key_discovery import discover_key_links
from quality_xy.loader import DatasetProfile
from quality_xy.sample_data import make_sample_datasets
from quality_xy.temporal_matcher import MatchConfig, XFactorSpec, build_wide_table


def test_discover_links_between_datasets():
    raw = make_sample_datasets()
    profiles = {k: DatasetProfile(k, v) for k, v in raw.items()}
    links = discover_key_links(profiles, min_intersection=3, min_overlap_ratio=0.05)
    assert len(links) >= 2
    pairs = {(l.dataset_a, l.dataset_b) for l in links} | {(l.dataset_b, l.dataset_a) for l in links}
    assert ("불량이력", "공정검사") in pairs or ("공정검사", "불량이력") in pairs


def test_build_wide_and_correlation():
    raw = make_sample_datasets()
    profiles = {k: DatasetProfile(k, v) for k, v in raw.items()}
    links = discover_key_links(profiles, min_intersection=3)
    graph = DatasetGraph(links)

    config = MatchConfig(
        anchor_dataset="불량이력",
        anchor_time_col="발생일시",
        y_column="불량점수",
        window_minutes=120,
        x_factors=[
            XFactorSpec(dataset="공정검사", column="압력값"),
            XFactorSpec(dataset="설비로그", column="온도"),
        ],
    )
    wide_df, detail_df = build_wide_table(profiles, graph, config)
    assert len(wide_df) == len(raw["불량이력"])
    assert "공정검사__압력값" in wide_df.columns

    matched_process = detail_df["공정검사__압력값_status"].astype(str).str.startswith("matched").sum()
    assert matched_process >= 10

    _, y_vs_x, valid_n = build_correlation_matrix(wide_df, "불량점수")
    assert valid_n >= 5
    assert not y_vs_x.empty
