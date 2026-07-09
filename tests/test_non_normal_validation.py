"""Non-normal 검증 수식 테스트."""
import numpy as np

from src.spc.non_normal_capability import percentile_capability
from src.spc.non_normal_validation import non_normal_metrics_from_values


def test_non_normal_ppk_matches_engine():
    vals = np.array([10.0, 10.1, 10.2, 9.9, 10.05, 10.15, 9.95, 10.0, 10.1, 10.2])
    usl, lsl = 11.0, 9.0
    nn = non_normal_metrics_from_values(vals, usl, lsl)
    direct = percentile_capability(vals, usl, lsl)
    assert abs(nn.ppk - direct.ppk) < 1e-9
    assert abs(nn.pp - direct.pp) < 1e-9
