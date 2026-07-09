"""관리도 Rule 카탈로그 — X-bar / R·S 분리 해석 테스트."""
from __future__ import annotations

from src.spc.control_chart_rules_catalog import load_control_chart_rules
from src.spc.spc_rules import RULE_DEFINITIONS, refresh_rule_definitions


def test_all_rules_have_split_interpretations():
    refresh_rule_definitions()
    rules = load_control_chart_rules()
    assert len(rules) == 9
    for rule in rules:
        assert rule.interpretation_xbar.strip(), f"{rule.id} missing interpretation_xbar"
        assert rule.interpretation_dispersion.strip(), f"{rule.id} missing interpretation_dispersion"
        assert rule.interpretation_xbar != rule.interpretation_dispersion, (
            f"{rule.id} xbar/rs interpretations should differ"
        )


def test_hugging_split_interpretation_content():
    refresh_rule_definitions()
    hug = next(r for r in load_control_chart_rules() if r.id == "HUGGING")
    assert "분해능" in hug.interpretation_xbar or "라운딩" in hug.interpretation_xbar
    assert "subgroup" in hug.interpretation_dispersion.lower() or "산포" in hug.interpretation_dispersion


def test_rule_definitions_export_split_fields():
    refresh_rule_definitions()
    spec = RULE_DEFINITIONS["SPEC_LIMIT_OUT"]
    assert "interpretation_xbar" in spec
    assert "interpretation_dispersion" in spec
    assert "규격" in spec["interpretation_xbar"] or "치우침" in spec["interpretation_xbar"]


def test_table_row_uses_split_columns():
    refresh_rule_definitions()
    row = load_control_chart_rules()[0].to_table_row()
    assert "X-bar 관리도 해석" in row
    assert "R/S 관리도 해석" in row
    assert "해석 의미" not in row
