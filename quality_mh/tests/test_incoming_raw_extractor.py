import pandas as pd

from quality_mh.incoming_raw_extractor import (
    aggregate_inspection_counts,
    extract_incoming_raw,
    parse_cheonan_production_plan,
    parse_inspection_list_raw,
)


def _sample_raw_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "양산입고\n검사레벨": ["샘플링", "전수", "무검사", "샘플링"],
            "수량": [100, 200, 300, 150],
            "년": [2025, 2025, 2025, 2025],
            "월": [1, 1, 2, 2],
            "품번": ["A", "B", "C", "D"],
        }
    )


def test_parse_inspection_list_raw():
    raw = parse_inspection_list_raw(_sample_raw_df(), year=2025)
    assert len(raw) == 4
    assert set(raw["inspection_type"]) == {"샘플링", "전수", "무검사"}


def test_aggregate_inspection_counts():
    raw = parse_inspection_list_raw(_sample_raw_df(), year=2025)
    pivot = aggregate_inspection_counts(raw, year=2025)
    assert pivot.counts["샘플링"][0] == 1
    assert pivot.counts["전수"][0] == 1
    assert pivot.counts["무검사"][1] == 1


def test_parse_cheonan_production_plan():
    plan = pd.DataFrame(
        [
            [None, None, None, None, None, None, "1월", "2월", "3월", "4월", "5월", "6월"],
            [None, "천안EBS", "천안", 1, "MEB", 100, 10, 20, 30, 40, 50, 60],
            [None, "합계", None, None, None, 200, 15, 25, 35, 45, 55, 65],
        ]
    )
    values = parse_cheonan_production_plan(plan, year=2025)
    assert values[0] == 15
    assert values[1] == 25
    assert values[2] == 35


def test_extract_incoming_raw():
    result = extract_incoming_raw(_sample_raw_df(), year=2025)
    assert len(result.records) == 4
    assert result.pivot.counts["샘플링"][0] == 1
    assert result.quantities.inbound_qty[0] == 300
