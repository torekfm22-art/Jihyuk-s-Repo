"""전수 데이터 모드 — 샘플링 생략, STDEV.P(모집단) σ_overall."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.spc.pipeline import SpcJobConfig, SpcPipeline
from src.spc.sampler import SampleSelector
from src.spc.statistics import SpcAnalyzer


def _make_df(n: int = 30) -> pd.DataFrame:
    return pd.DataFrame({
        "value": 10.0 + np.linspace(0, 0.01, n),
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="h"),
    })


def test_select_full_population_xbar_assigns_subgroups():
    df = _make_df(27)
    sample, sg = SampleSelector(df).select_full_population(subgroup_size=5, for_xbar=True)
    assert sg == 5
    assert len(sample) == 25
    assert sample["subgroup_id"].nunique() == 5
    assert (sample["sampling_strategy"] == "full_population").all()


def test_select_full_population_imr_uses_all_rows():
    df = _make_df(12)
    sample, sg = SampleSelector(df).select_full_population(subgroup_size=5, for_xbar=False)
    assert sg is None
    assert len(sample) == 12
    assert "subgroup_id" not in sample.columns


def test_capability_population_std_uses_stdev_p():
    data = np.array([9.8, 10.0, 10.1, 10.2, 10.0])
    sample_std = SpcAnalyzer(population_std=False).capability(data, usl=10.5, lsl=9.5)
    pop_std = SpcAnalyzer(population_std=True).capability(data, usl=10.5, lsl=9.5)
    assert pop_std.std_overall == float(np.std(data, ddof=0))
    assert sample_std.std_overall == float(np.std(data, ddof=1))
    assert pop_std.pp != sample_std.pp


def test_pipeline_full_population_skips_sampling(tmp_path):
    df = _make_df(50)
    xlsx = tmp_path / "full.xlsx"
    df.to_excel(xlsx, index=False)

    cfg = SpcJobConfig(
        input_files=[str(xlsx)],
        usl=10.5,
        lsl=9.5,
        subgroup_size=5,
        n_subgroups=10,
        use_full_population=True,
        chart_type="xbar_s",
        save_reports=False,
        output_dir=str(tmp_path),
    )
    result = SpcPipeline(cfg).run()
    assert result.sample_count == 50
    assert "전수 데이터" in (result.sampling_note or "")
    assert result.analysis is not None
    assert result.analysis.metadata.get("population_std") is True
    cap = result.analysis.capability
    assert cap is not None
    values = result.sample_df["value"].to_numpy()
    assert cap.std_overall == float(np.std(values, ddof=0))
