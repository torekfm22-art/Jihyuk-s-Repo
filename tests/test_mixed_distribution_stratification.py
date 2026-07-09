"""혼합분포 판정 · 재구성 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.spc.mixed_distribution_stratification import (
    _score_candidate,
    _sigma_ratio_score,
    analyze_group_slice,
    build_split_candidates,
    classify_stratification_column,
    diagnose_mixed_distribution,
    is_valid_stratification_split_column,
    run_stratification_study,
    run_stratified_reanalysis,
)
from src.spc.stratified_subgroup_builder import reconstruct_stratified_subgroups


def _mixed_df() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-01-01 08:00:00")
    for shift, mean in [("주간", 10.0), ("야간", 10.08)]:
        for i in range(60):
            rows.append({
                "value": mean + np.random.default_rng(i).normal(0, 0.02),
                "timestamp": base + pd.Timedelta(hours=i if shift == "주간" else i + 100),
                "shift": shift,
                "lot": f"LOT-{i // 10}",
                "measurement_point": "3호기",
            })
    return pd.DataFrame(rows)


def test_build_split_candidates_excludes_continuous_measurement():
    """연속 측정치(고유값 많음·소수)는 항목명과 무관하게 제외."""
    df = _mixed_df()
    rng = np.random.default_rng(0)
    df["스테이터 무게"] = 144.0 + rng.normal(0, 0.01, len(df))
    df["바니쉬 도포중량"] = df["value"]
    cands = build_split_candidates(df, fixed_columns=["measurement_point"])
    cols_used = {c for _, cs in cands for c in cs}
    assert "스테이터 무게" not in cols_used
    assert "바니쉬 도포중량" not in cols_used
    assert classify_stratification_column(df, "스테이터 무게") == "exclude"
    assert not is_valid_stratification_split_column(df, "스테이터 무게")


def test_build_split_candidates_includes_factory_specific_categorical():
    """공장별 비표준 항목명도 범주형이면 후보에 포함."""
    df = _mixed_df()
    df["WRK_GRP_ALPHA"] = np.where(df.index % 3 == 0, "A", np.where(df.index % 3 == 1, "B", "C"))
    assert classify_stratification_column(df, "WRK_GRP_ALPHA") == "process"
    cands = build_split_candidates(df, fixed_columns=["measurement_point"])
    cols_used = {c for _, cs in cands for c in cs}
    assert "WRK_GRP_ALPHA" in cols_used


def test_build_split_candidates_infers_shift_without_shift_column():
    """교대 컬럼 없어도 측정일시로 교대 후보 생성."""
    df = _mixed_df().drop(columns=["shift"])
    cands = build_split_candidates(df)
    bases = [b for b, _ in cands]
    assert any("교대" in b for b in bases), f"expected shift candidate, got {bases}"


def test_reconstruct_rejects_measurement_split_column():
    df = _mixed_df().head(20)
    df["스테이터 무게"] = df["value"] + 100
    import pytest
    with pytest.raises(ValueError, match="공정·조건"):
        reconstruct_stratified_subgroups(df, ["스테이터 무게"], subgroup_size=5, min_subgroup_count=2)


def test_build_split_candidates_when_measurement_point_fixed_single_value():
    """측정호기 1개 값으로 필터된 경우에도 LOT·날짜 후보가 생성되어야 함."""
    df = _mixed_df()
    df["measurement_point"] = "3호기"
    cands = build_split_candidates(df, fixed_columns=["measurement_point"])
    bases = [b for b, _ in cands]
    assert any("LOT" in b for b in bases), f"expected LOT candidate, got {bases}"
    assert any("날짜" in b for b in bases), f"expected date candidate, got {bases}"


def test_build_split_candidates_real_export_with_mp_fixed():
    """실제 export 형식 — 측정포인트 고정 시 후보 생성."""
    import pandas as pd
    from pathlib import Path

    path = Path("data/output/stratified_sample_1_20260624_151625.csv")
    if not path.exists():
        return
    df = pd.read_csv(path, nrows=200)
    cands = build_split_candidates(df, fixed_columns=["measurement_point"])
    assert cands, "expected at least one split candidate for real export data"


def test_reconstruct_subgroups_respects_shift_boundary():
    df = _mixed_df().head(30)
    out, _ = reconstruct_stratified_subgroups(df, ["shift"], subgroup_size=5, min_subgroup_count=2)
    assert "subgroup_id" in out.columns
    for sg, grp in out.groupby("subgroup_id"):
        assert grp["shift"].nunique() == 1, f"subgroup {sg} mixed shift"


def test_diagnose_mixed_distribution_suspected():
    df = _mixed_df()
    diag = diagnose_mixed_distribution(df, usl=10.5, lsl=9.5)
    assert diag.suspected
    assert diag.sigma_ratio is None or diag.sigma_ratio > 0


def test_stratification_study_ranks_shift():
    df = _mixed_df()
    study = run_stratification_study(df, usl=10.5, lsl=9.5, min_subgroup_count=2)
    assert study.candidates
    assert study.candidates[0].rank == 1
    assert study.candidates[0].recommendation_judgment
    assert 0 <= study.candidates[0].total_score <= 100


def test_sigma_ratio_score_buckets():
    assert _sigma_ratio_score(1.1) == 30
    assert _sigma_ratio_score(1.4) == 20
    assert _sigma_ratio_score(1.8) == 10
    assert _sigma_ratio_score(2.5) == 0


def test_score_candidate_max_100():
    df = _mixed_df()
    overall = analyze_group_slice(df, group_key="전체", usl=10.5, lsl=9.5, min_subgroup_count=2)
    groups = [
        analyze_group_slice(grp, group_key=str(k), usl=10.5, lsl=9.5, min_subgroup_count=2)
        for k, grp in df.groupby("shift")
    ]
    total, _, _, judgment = _score_candidate(overall, groups, "교대")
    assert total <= 100
    assert judgment


def test_reconstruct_subgroups_high_cardinality_lot_fallback():
    rows = []
    base = pd.Timestamp("2026-01-01 08:00:00")
    for i in range(30):
        rows.append({
            "value": 10.0 + np.random.default_rng(i).normal(0, 0.02),
            "timestamp": base + pd.Timedelta(minutes=i),
            "shift": "주간",
            "lot": f"LOT-{i}",
            "measurement_point": "3호기",
        })
    df = pd.DataFrame(rows)
    out, _ = reconstruct_stratified_subgroups(df, ["shift"], subgroup_size=5, min_subgroup_count=2)
    assert not out.empty
    assert out["subgroup_id"].nunique() >= 2


def test_stratified_reanalysis_produces_comparison():
    df = _mixed_df()
    result = run_stratified_reanalysis(
        df, ["shift"], usl=10.5, lsl=9.5, min_subgroup_count=2,
    )
    assert len(result.comparison_rows) >= 2
    assert not result.sample_df.empty
    assert "split_key" in result.sample_df.columns or "strat_group_key" in result.sample_df.columns


def test_excel_export_builds_bytes():
    from src.spc.mixed_distribution_excel_export import build_reconstructed_excel_bytes

    df = _mixed_df()
    study = run_stratification_study(df, usl=10.5, lsl=9.5, min_subgroup_count=2)
    rebuild = run_stratified_reanalysis(df, ["shift"], usl=10.5, lsl=9.5, min_subgroup_count=2)
    data, name = build_reconstructed_excel_bytes(
        original_df=df,
        study=study,
        reconstructed_df=rebuild.sample_df,
        spc_groups=rebuild.after_groups,
    )
    assert len(data) > 5000
    assert name.startswith("spc_reconstructed_sample_")
