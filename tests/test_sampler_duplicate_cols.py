"""sampler — 중복 process 컬럼 대응."""
import pandas as pd

from src.spc.sampler import SampleSelector


def test_prepare_sampling_with_duplicate_process_columns():
    df = pd.DataFrame({
        "process": ["P1", "P2", "P3"],
        "value": [1.0, 2.0, 3.0],
        "timestamp": pd.to_datetime(["2026-01-01 10:00", "2026-01-01 11:00", "2026-01-01 12:00"]),
    })
    # pandas duplicate column names
    dup = pd.concat([df[["process"]], df[["process"]], df[["value", "timestamp"]]], axis=1)
    dup.columns = ["process", "process", "value", "timestamp"]

    prepared = SampleSelector(dup)._prepare_for_sampling()
    assert "_block_process" in prepared.columns
    assert len(prepared["_block_process"]) == 3
