"""편측 공차 — USL/LSL 해석 및 공정능력 산출."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.spc.spec_limits import resolve_effective_spec_limits, ui_spec_mode_to_type
from src.spc.statistics import SpcAnalyzer


def test_ui_spec_mode_to_type():
    assert ui_spec_mode_to_type("편측 — 상한치") == "upper_only"
    assert ui_spec_mode_to_type("양측 공차") == "two_sided"


def test_upper_only_ignores_excel_lsl_column():
    df = pd.DataFrame({"value": [0.2, 0.3], "usl": [5.0, 5.0], "lsl": [0.0, 0.0]})
    usl, lsl, spec = resolve_effective_spec_limits(5.0, None, df, spec_type="upper_only")
    assert usl == 5.0
    assert lsl is None
    assert spec == "upper_only"


def test_without_spec_type_auto_fills_lsl_from_excel():
    df = pd.DataFrame({"value": [0.2], "usl": [5.0], "lsl": [0.0]})
    usl, lsl, spec = resolve_effective_spec_limits(5.0, None, df, spec_type=None)
    assert lsl == 0.0
    assert spec == "two_sided"


def test_upper_only_capability_not_two_sided_cp():
    """편측 상한 USL=5 — Cp=(USL-LSL)/6σ 사용 금지, Cpk=CWU."""
    mean = 0.22028
    sw = 0.05705932932072227
    usl = 5.0
    data = np.full(125, mean)
    cap = SpcAnalyzer().capability(data, usl=usl, lsl=None, sigma_within=sw)
    assert cap.spec_type == "upper_only"
    assert math.isnan(cap.cp)
    assert math.isnan(cap.pp)
    expected_cpk = (usl - mean) / (3 * sw)
    assert abs(cap.cpk - expected_cpk) < 1e-6
    assert abs(cap.cpu - expected_cpk) < 1e-6
    # 양측 LSL=0 이면 Cp≈14.6 — 편측에서는 나오면 안 됨
    two_sided_cp = (usl - 0.0) / (6 * sw)
    assert two_sided_cp > 10
    assert math.isnan(cap.cp)


def test_user_scenario_two_sided_cp_if_lsl_zero():
    mean = 0.22028
    sw = 0.05705932932072227
    usl = 5.0
    data = np.full(125, mean)
    cap = SpcAnalyzer().capability(data, usl=usl, lsl=0.0, sigma_within=sw)
    assert cap.spec_type == "two_sided"
    assert abs(cap.cp - 14.604681535061284) < 0.001
