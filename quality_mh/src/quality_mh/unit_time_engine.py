"""MODAPTS 기반 단위시간 엔진."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from quality_mh.audit_engine import AuditEngine
from quality_mh.constants import (
    CONFIRMED_MOD_TO_MINUTES,
    CONFIRMED_STEP_LENGTH_M,
    RuleStatus,
    ValidationStatus,
)
from quality_mh.models import RuleBase, UnitTimeInput
from quality_mh.rule_loader import load_unit_time_rules


def distance_to_steps(distance_m: float, step_length_m: float = CONFIRMED_STEP_LENGTH_M) -> float:
    if step_length_m <= 0:
        raise ValueError("step_length_m must be positive")
    return distance_m / step_length_m


def mod_to_minutes(mod_value: float, mod_factor: float = CONFIRMED_MOD_TO_MINUTES) -> float:
    return mod_value * mod_factor


def steps_to_mod(steps: float, rule: RuleBase | None = None) -> tuple[float | None, ValidationStatus, str]:
    """걸음수→MOD 변환. 규칙 미확정 시 None 반환."""
    if rule and rule.parameters.get("steps_to_mod_rule") not in (None, "RULE_NOT_CONFIRMED"):
        expr = rule.parameters.get("steps_to_mod_expression")
        if expr == "steps":
            return steps, ValidationStatus.OK, "steps_to_mod = steps (rule parameter)"
    return None, ValidationStatus.RULE_NOT_CONFIRMED, "걸음수→MOD 변환 규칙 미확정"


class UnitTimeEngine:
    def __init__(self, rules: list[RuleBase] | None = None, audit: AuditEngine | None = None) -> None:
        self.rules = rules or load_unit_time_rules()
        self.audit = audit or AuditEngine()
        self._rule_map = {r.rule_id: r for r in self.rules}

    def _get_rule(self, rule_id: str) -> RuleBase | None:
        return self._rule_map.get(rule_id)

    def calc_movement_minutes(
        self,
        distance_m: float,
        *,
        weight_kg: float | None = None,
        factory: str = "*",
        line: str = "*",
    ) -> dict[str, Any]:
        rule_id = "UT-MOVEMENT-HEAVY" if weight_kg and weight_kg >= 20 else "UT-MOVEMENT-BASE"
        rule = self._get_rule(rule_id)
        if not rule:
            return {"movement_min": None, "status": ValidationStatus.RULE_NOT_CONFIRMED, "rule_id": rule_id}

        step_len = float(rule.parameters.get("step_length_m", CONFIRMED_STEP_LENGTH_M))
        mod_factor = float(rule.parameters.get("mod_to_minutes", CONFIRMED_MOD_TO_MINUTES))
        steps = distance_to_steps(distance_m, step_len)
        mod_value, mod_status, mod_msg = steps_to_mod(steps, rule)

        status = ValidationStatus.OK if mod_status == ValidationStatus.OK else ValidationStatus.RULE_NOT_CONFIRMED
        movement_min = mod_to_minutes(mod_value, mod_factor) if mod_value is not None else None

        self.audit.log_rule_application(
            "unit_time_engine",
            rule_id,
            source_file=rule.source_file,
            source_sheet=rule.source_sheet,
            status=RuleStatus(rule.status.value),
            message=mod_msg,
            detail={"distance_m": distance_m, "steps": steps, "movement_min": movement_min},
        )
        return {
            "movement_min": movement_min,
            "steps": steps,
            "mod_value": mod_value,
            "status": status,
            "message": mod_msg,
            "rule_id": rule_id,
        }

    def calc_action_minutes(
        self,
        mod_value: float,
        auxiliary_rate: float | None = None,
    ) -> dict[str, Any]:
        rule = self._get_rule("UT-ACTION-MOD")
        if not rule:
            return {"action_min": None, "status": ValidationStatus.RULE_NOT_CONFIRMED}

        if auxiliary_rate is None:
            default_rate = rule.parameters.get("default_auxiliary_rate")
            if default_rate is None:
                return {
                    "action_min": None,
                    "status": ValidationStatus.MANUAL_CONFIRM_REQUIRED,
                    "message": "보조공수율 미입력 - rule 또는 입력값 필요",
                    "rule_id": "UT-ACTION-MOD",
                }
            auxiliary_rate = float(default_rate)

        labor_subtotal = mod_value * (1 + auxiliary_rate)
        action_min = mod_to_minutes(labor_subtotal)

        self.audit.log_rule_application(
            "unit_time_engine",
            "UT-ACTION-MOD",
            source_file=rule.source_file,
            source_sheet=rule.source_sheet,
            status=RuleStatus.CONFIRMED,
            detail={"mod_value": mod_value, "auxiliary_rate": auxiliary_rate, "action_min": action_min},
        )
        return {
            "action_min": action_min,
            "labor_subtotal": labor_subtotal,
            "status": ValidationStatus.OK,
            "rule_id": "UT-ACTION-MOD",
        }

    def calc_wait_minutes(self, measured_wait_sec: float | None = None, cycle_count: int | None = None) -> dict[str, Any]:
        if measured_wait_sec is not None:
            rule = self._get_rule("UT-WAIT-MEASURED")
            wait_min = measured_wait_sec / 60.0
            self.audit.log_rule_application(
                "unit_time_engine",
                "UT-WAIT-MEASURED",
                status=RuleStatus.CONFIRMED,
                detail={"measured_wait_sec": measured_wait_sec, "wait_min": wait_min},
            )
            return {"wait_min": wait_min, "status": ValidationStatus.OK, "rule_id": "UT-WAIT-MEASURED"}

        if cycle_count is not None:
            rule = self._get_rule("UT-WAIT-CYCLE")
            self.audit.log_rule_application(
                "unit_time_engine",
                "UT-WAIT-CYCLE",
                status=RuleStatus.RULE_NOT_CONFIRMED,
                message="cycle_time_min 미확정",
            )
            return {
                "wait_min": None,
                "status": ValidationStatus.RULE_NOT_CONFIRMED,
                "message": "작동대기 cycle_time 미확정",
                "rule_id": "UT-WAIT-CYCLE",
            }

        return {"wait_min": 0.0, "status": ValidationStatus.OK, "rule_id": ""}

    def calc_unit_time(self, inp: UnitTimeInput) -> dict[str, Any]:
        parts: dict[str, Any] = {}
        statuses: list[ValidationStatus] = []
        messages: list[str] = []
        applied_rules: list[str] = []

        if inp.movement_distance_m is not None:
            mv = self.calc_movement_minutes(
                inp.movement_distance_m,
                weight_kg=inp.weight_kg,
                factory=inp.factory_name,
                line=inp.line_name,
            )
            parts["movement_min"] = mv.get("movement_min")
            statuses.append(mv["status"])
            if mv.get("message"):
                messages.append(mv["message"])
            applied_rules.append(mv["rule_id"])

        action_min = None
        if inp.mod_value is not None:
            act = self.calc_action_minutes(inp.mod_value, inp.auxiliary_rate)
            action_min = act.get("action_min")
            parts["action_min"] = action_min
            statuses.append(act["status"])
            if act.get("message"):
                messages.append(act["message"])
            applied_rules.append(act.get("rule_id", "UT-ACTION-MOD"))

        wait = self.calc_wait_minutes(inp.measured_wait_sec)
        parts["wait_min"] = wait.get("wait_min", 0.0)
        statuses.append(wait["status"])
        if wait.get("message"):
            messages.append(wait["message"])
        if wait.get("rule_id"):
            applied_rules.append(wait["rule_id"])

        movement = parts.get("movement_min")
        action = parts.get("action_min")
        wait_min = parts.get("wait_min") or 0.0

        movement_missing = inp.movement_distance_m is not None and movement is None
        action_missing = inp.mod_value is not None and action is None

        if action_missing:
            unit_time = None
            final_status = ValidationStatus.MANUAL_CONFIRM_REQUIRED
        else:
            unit_time = (movement or 0.0) + (action or 0.0) + (wait_min or 0.0)
            if movement_missing:
                final_status = ValidationStatus.NEEDS_REVIEW
                messages.append("이동시간 미산출(걸음수→MOD 미확정) - 동작+대기만 반영")
            elif any(s in {ValidationStatus.RULE_NOT_CONFIRMED, ValidationStatus.MANUAL_CONFIRM_REQUIRED} for s in statuses):
                final_status = ValidationStatus.NEEDS_REVIEW
            else:
                final_status = ValidationStatus.OK

        self.audit.log_calculation(
            "unit_time_total",
            "unit_time_engine",
            input_summary=f"{inp.factory_name}/{inp.inspection_name}",
            output_summary=str(unit_time),
            rule_id="UT-TOTAL-SUM",
            status=final_status,
            message="; ".join(messages),
        )

        return {
            "factory_name": inp.factory_name,
            "line_name": inp.line_name,
            "inspection_name": inp.inspection_name,
            "movement_min": parts.get("movement_min"),
            "action_min": parts.get("action_min"),
            "wait_min": parts.get("wait_min"),
            "unit_time_min": unit_time,
            "applied_rules": applied_rules,
            "status": final_status,
            "message": "; ".join(messages),
            "source_file": inp.source_file,
            "source_sheet": inp.source_sheet,
        }

    def calc_from_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, row in df.iterrows():
            inp = UnitTimeInput(
                factory_name=str(row.get("factory_name", "")),
                line_name=str(row.get("line_name", "")),
                inspection_name=str(row.get("inspection_name", "")),
                movement_distance_m=_safe_float(row.get("movement_distance_m")),
                weight_kg=_safe_float(row.get("weight_kg")),
                mod_value=_safe_float(row.get("mod_value")),
                measured_wait_sec=_safe_float(row.get("measured_wait_sec")),
                auxiliary_rate=_safe_float(row.get("auxiliary_rate")),
                source_file=str(row.get("source_file", "")),
                source_sheet=str(row.get("source_sheet", "")),
            )
            rows.append(self.calc_unit_time(inp))
        return pd.DataFrame(rows)


def _safe_float(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
