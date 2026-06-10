from quality_mh.frequency_engine import FrequencyEngine
from quality_mh.manpower_engine import ManpowerEngine
from quality_mh.mh_engine import MhEngine
from quality_mh.pipeline import QualityMhPipeline
from quality_mh.unit_time_engine import UnitTimeEngine


def test_mh_equals_frequency_times_unit_time(demo_frequency_df, demo_unit_time_df):
    freq_engine = FrequencyEngine()
    ut_engine = UnitTimeEngine()
    mh_engine = MhEngine()

    freq = freq_engine.apply_raw_count(demo_frequency_df)
    ut = ut_engine.calc_from_dataframe(demo_unit_time_df)
    mh = mh_engine.calc_mh(freq, ut)

    assert not mh.empty
    valid = mh.dropna(subset=["mh_value"])
    for _, row in valid.iterrows():
        expected = row["frequency_value"] * row["unit_time_value"]
        assert row["mh_value"] == expected


def test_pipeline_demo():
    pipeline = QualityMhPipeline()
    state = pipeline.run_demo()
    state = pipeline.run_calculation(state)
    assert not state.frequency_df.empty
    assert not state.unit_time_df.empty
    assert not state.mh_df.empty


def test_manpower_placeholder():
    engine = ManpowerEngine()
    result = engine.calc_headcount(10000.0, factory="김천")
    assert result.standard_headcount is None
    assert result.status.value == "RULE_NOT_CONFIRMED"
