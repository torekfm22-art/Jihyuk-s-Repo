"""Rule JSON 로더."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_mh.models import RuleBase, StandardTask

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = PROJECT_ROOT / "rules"


def load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_standard_tasks(path: Path | None = None) -> list[StandardTask]:
    data = load_json(path or RULES_DIR / "standard_master.json")
    return [StandardTask(**t) for t in data.get("tasks", [])]


def load_rules(path: Path) -> list[RuleBase]:
    data = load_json(path)
    return [RuleBase(**r) for r in data.get("rules", [])]


def load_frequency_rules() -> list[RuleBase]:
    return load_rules(RULES_DIR / "frequency_rules.json")


def load_unit_time_rules() -> list[RuleBase]:
    return load_rules(RULES_DIR / "unit_time_rules.json")


def load_manpower_rules() -> list[RuleBase]:
    return load_rules(RULES_DIR / "manpower_rules.json")


def load_column_mapping(path: Path | None = None) -> dict[str, Any]:
    mapping_path = path or PROJECT_ROOT / "config" / "column_mapping.json"
    return load_json(mapping_path)
