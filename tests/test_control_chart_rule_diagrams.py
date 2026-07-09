"""관리도 Rule 도식 SVG 테스트."""
from __future__ import annotations

from src.spc.control_chart_rules_catalog import load_control_chart_rules
from src.spc_streamlit.control_chart_rule_diagrams import rule_diagram_svg


def test_all_rules_have_diagrams():
    for rule in load_control_chart_rules():
        svg = rule_diagram_svg(rule.id)
        assert "<svg" in svg
        assert "</svg>" in svg
