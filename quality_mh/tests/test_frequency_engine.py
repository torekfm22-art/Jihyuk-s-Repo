from quality_mh.frequency_engine import FrequencyEngine


def test_raw_count_aggregation(demo_frequency_df):
    engine = FrequencyEngine()
    result = engine.apply_raw_count(demo_frequency_df)
    assert not result.empty
    assert "frequency_value" in result.columns
    assert result["frequency_value"].sum() == 245


def test_pivot_pass_through(demo_frequency_df):
    engine = FrequencyEngine()
    df = demo_frequency_df.rename(columns={"quantity": "frequency_value"})
    result = engine.apply_pivot_pass_through(df)
    assert result["frequency_value"].sum() == 245
