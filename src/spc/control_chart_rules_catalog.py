"""관리도 해석 규칙 카탈로그 — JSON 기반 (UI·엔진 공통)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "control_chart_rules.json"


@dataclass(frozen=True)
class ControlChartRule:
    id: str
    category: str
    rule_name: str
    condition: str
    interpretation: str
    interpretation_xbar: str = ""
    interpretation_dispersion: str = ""
    tooltip: str = ""
    detection: dict[str, Any] = field(default_factory=dict)

    def to_table_row(self) -> dict[str, str]:
        return {
            "구분": self.category,
            "규칙명": self.rule_name,
            "조건": self.condition,
            "X-bar 관리도 해석": self.interpretation_xbar or self.interpretation,
            "R/S 관리도 해석": self.interpretation_dispersion or self.interpretation,
        }


@lru_cache(maxsize=1)
def load_control_chart_rules() -> list[ControlChartRule]:
    data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return [
        ControlChartRule(
            id=r["id"],
            category=r["category"],
            rule_name=r["rule_name"],
            condition=r["condition"],
            interpretation=r["interpretation"],
            interpretation_xbar=r.get("interpretation_xbar", r["interpretation"]),
            interpretation_dispersion=r.get("interpretation_dispersion", r["interpretation"]),
            tooltip=r.get("tooltip", ""),
            detection=r.get("detection", {}),
        )
        for r in data["rules"]
    ]


@lru_cache(maxsize=1)
def load_process_state_labels() -> dict[str, str]:
    data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return data.get("process_state", {
        "in_control_label": "관리상태",
        "out_of_control_label": "비관리상태",
    })


def rule_by_id(rule_id: str) -> ControlChartRule | None:
    return next((r for r in load_control_chart_rules() if r.id == rule_id), None)


def rules_as_dataframe_rows() -> list[dict[str, str]]:
    return [r.to_table_row() for r in load_control_chart_rules()]
