"""단위시간 엔진 테스트 - 확인된 산식만 검증."""
import math

import pytest

from quality_mh.constants import CONFIRMED_MOD_TO_MINUTES, CONFIRMED_STEP_LENGTH_M
from quality_mh.models import UnitTimeInput
from quality_mh.unit_time_engine import (
    UnitTimeEngine,
    distance_to_steps,
    mod_to_minutes,
)


def test_distance_to_steps():
    assert distance_to_steps(12.0) == pytest.approx(12.0 / CONFIRMED_STEP_LENGTH_M)


def test_mod_to_minutes():
    assert mod_to_minutes(10.0) == pytest.approx(10.0 * CONFIRMED_MOD_TO_MINUTES)


def test_action_time_with_auxiliary_rate():
    engine = UnitTimeEngine()
    result = engine.calc_action_minutes(mod_value=5.0, auxiliary_rate=0.10)
    expected_mod = 5.0 * 1.10
    assert result["action_min"] == pytest.approx(mod_to_minutes(expected_mod))
    assert result["status"].value == "OK"


def test_wait_measured_seconds():
    engine = UnitTimeEngine()
    result = engine.calc_wait_minutes(measured_wait_sec=60)
    assert result["wait_min"] == pytest.approx(1.0)


def test_movement_needs_review_when_steps_to_mod_unconfirmed():
    engine = UnitTimeEngine()
    result = engine.calc_movement_minutes(12.0)
    assert result["movement_min"] is None
    assert result["status"].value == "RULE_NOT_CONFIRMED"


def test_unit_time_action_only(demo_unit_time_df):
    engine = UnitTimeEngine()
    row = demo_unit_time_df.iloc[1]
    inp = UnitTimeInput(
        factory_name=row["factory_name"],
        line_name=row["line_name"],
        inspection_name=row["inspection_name"],
        mod_value=row["mod_value"],
        auxiliary_rate=row["auxiliary_rate"],
    )
    result = engine.calc_unit_time(inp)
    assert result["unit_time_min"] is not None
    assert result["action_min"] == pytest.approx(mod_to_minutes(3.0 * 1.10))
