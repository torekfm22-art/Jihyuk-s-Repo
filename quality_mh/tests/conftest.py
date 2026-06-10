import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def demo_frequency_df():
    from quality_mh.sample_data import build_demo_frequency_df
    return build_demo_frequency_df()


@pytest.fixture
def demo_unit_time_df():
    from quality_mh.sample_data import build_demo_unit_time_df
    return build_demo_unit_time_df()
