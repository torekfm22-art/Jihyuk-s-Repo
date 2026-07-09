"""편측 공차 — CWU/CWL 공정능력 산출."""
from __future__ import annotations

import math

import numpy as np

from src.spc.statistics import SpcAnalyzer, infer_spec_type


def test_infer_spec_type():
    assert infer_spec_type(10.0, 9.0) == "two_sided"
    assert infer_spec_type(10.0, None) == "upper_only"
    assert infer_spec_type(None, 9.0) == "lower_only"


def test_upper_only_cwu():
    rng = np.random.default_rng(1)
    data = rng.normal(9.8, 0.05, 50)
    usl = 10.0
    analyzer = SpcAnalyzer()
    cap = analyzer.capability(data, usl=usl, lsl=None, sigma_within=0.05)
    assert cap.spec_type == "upper_only"
    expected = (usl - cap.mean) / (3 * 0.05)
    assert abs(cap.cpk - expected) < 1e-6
    assert abs(cap.cpu - expected) < 1e-6
    assert math.isnan(cap.cp)
    assert math.isnan(cap.cpl)


def test_lower_only_cwl():
    rng = np.random.default_rng(2)
    data = rng.normal(10.2, 0.05, 50)
    lsl = 10.0
    analyzer = SpcAnalyzer()
    cap = analyzer.capability(data, usl=None, lsl=lsl, sigma_within=0.05)
    assert cap.spec_type == "lower_only"
    expected = (cap.mean - lsl) / (3 * 0.05)
    assert abs(cap.cpk - expected) < 1e-6
    assert abs(cap.cpl - expected) < 1e-6
    assert math.isnan(cap.cp)
    assert math.isnan(cap.cpu)
