"""관리도 해석 규칙 — JSON 카탈로그 re-export (구 spc_rules 대체)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from src.spc.control_chart_rules_catalog import (
    ControlChartRule,
    load_control_chart_rules,
    load_process_state_labels,
    rule_by_id,
    rules_as_dataframe_rows,
)

RuleId = str


@lru_cache(maxsize=1)
def _rule_definitions() -> dict[str, dict[str, Any]]:
    return {
        r.id: {
            "rule_name": r.rule_name,
            "category": r.category,
            "description": r.condition,
            "condition": r.condition,
            "interpretation": r.interpretation,
            "interpretation_xbar": r.interpretation_xbar,
            "interpretation_dispersion": r.interpretation_dispersion,
            "tooltip": r.tooltip,
        }
        for r in load_control_chart_rules()
    }


RULE_DEFINITIONS: dict[str, dict[str, Any]] = _rule_definitions()


def refresh_rule_definitions() -> None:
    """테스트·핫리로드용 캐시 초기화."""
    _rule_definitions.cache_clear()
    from src.spc.control_chart_rules_catalog import load_control_chart_rules as _l

    _l.cache_clear()
    load_process_state_labels.cache_clear()
    global RULE_DEFINITIONS
    RULE_DEFINITIONS = _rule_definitions()
