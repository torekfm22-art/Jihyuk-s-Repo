import pandas as pd

from quality_mh.incoming_frequency_analyzer import (
    YearPivotInput,
    YearQuantityInput,
    analyze_incoming_frequency_year,
    compute_type_shares,
    parse_pivot_sheet,
    to_frequency_dataframe,
)


def _sample_pivot_2025() -> YearPivotInput:
    return YearPivotInput(
        year=2025,
        actual_months=7,
        counts={
            "샘플링": [802, 1109, 1030, 1169, 961, 1087, 1082] + [None] * 5,
            "전수": [8, 23, 11, 45, 37, 31, 25] + [None] * 5,
            "무검사": [630, 732, 988, 1178, 1001, 974, 993] + [None] * 5,
        },
    )


def _sample_quantities_2025() -> YearQuantityInput:
    inbound = [
        33605194, 40784643, 44892106, 50716597, 42536882, 42414048, 39484678,
        None, None, None, None, None,
    ]
    production = [
        136627, 167216, 178945, 181072, 140885, 159858, 152513,
        150802, 215002, 173748, 188310, 200548,
    ]
    return YearQuantityInput(year=2025, inbound_qty=inbound, production_qty=production)


def test_compute_type_shares():
    pivot = _sample_pivot_2025()
    shares = compute_type_shares(pivot.counts, months=7)
    assert abs(sum(shares.values()) - 1.0) < 1e-6
    assert shares["샘플링"] > shares["전수"]


def test_analyze_projects_from_august():
    pivot = _sample_pivot_2025()
    qty = _sample_quantities_2025()
    result = analyze_incoming_frequency_year(
        pivot=pivot,
        quantities=qty,
        projection_start_month=8,
    )
    aug_sampling = result.summary_long[
        (result.summary_long["metric"] == "입고검사 건수")
        & (result.summary_long["inspection_type"] == "샘플링")
    ]["m08"].iloc[0]
    assert aug_sampling is not None
    assert aug_sampling > 0

    sep_sampling = result.summary_long[
        (result.summary_long["metric"] == "입고검사 건수")
        & (result.summary_long["inspection_type"] == "샘플링")
    ]["m09"].iloc[0]
    assert sep_sampling is not None
    assert sep_sampling > aug_sampling * 0.5


def test_parse_pivot_sheet():
    df = pd.DataFrame(
        [
            ["검사유형", "1", "2", "3", "총합계"],
            ["무검사", 10, 20, 30, 60],
            ["샘플링", 100, 110, 120, 330],
            ["전수", 1, 2, 3, 6],
        ]
    )
    parsed = parse_pivot_sheet(df, year=2024)
    assert parsed.counts["샘플링"][:3] == [100.0, 110.0, 120.0]
    assert parsed.counts["무검사"][:3] == [10.0, 20.0, 30.0]
    assert parsed.actual_months == 3


def test_to_frequency_dataframe():
    pivot = _sample_pivot_2025()
    qty = _sample_quantities_2025()
    result = analyze_incoming_frequency_year(pivot=pivot, quantities=qty, projection_start_month=13)
    freq = to_frequency_dataframe(result.summary_long)
    assert not freq.empty
    assert set(freq["inspection_type"]) <= {"샘플링", "전수", "무검사"}
    assert (freq["domain"] == "입고").all()
