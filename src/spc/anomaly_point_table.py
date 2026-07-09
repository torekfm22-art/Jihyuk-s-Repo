"""관리도 이상점 — 포인트별 Rule·조건·해석 표."""
from __future__ import annotations

import pandas as pd

from src.spc.decision_models import SpcDecisionResult
from src.spc.spc_rules import RULE_DEFINITIONS
from src.spc.statistics import SpcAnalysisResult


def _rule_condition(rule_id: str | None, fallback: str = "") -> str:
    if rule_id and rule_id in RULE_DEFINITIONS:
        return str(RULE_DEFINITIONS[rule_id].get("condition", fallback))
    return fallback


def _rule_interpretation(rule_id: str | None, fallback: str = "") -> str:
    if rule_id and rule_id in RULE_DEFINITIONS:
        return str(RULE_DEFINITIONS[rule_id].get("interpretation", fallback))
    return fallback


def build_anomaly_point_table(
    decision: SpcDecisionResult,
    analysis: SpcAnalysisResult | None = None,
) -> pd.DataFrame:
    """이상점별 Rule명·조건·데이터 값·해석 의미 표."""
    rows: list[dict[str, str]] = []
    cc = decision.control_chart
    point_label = "Subgroup" if analysis and analysis.chart_type in ("xbar_s", "xbar_r") else "Point"

    def append(
        pid: int,
        rule_name: str,
        criterion: str,
        interpretation: str,
        data_value: str = "",
        rule_id: str = "",
    ) -> None:
        rows.append({
            point_label: str(pid),
            "규칙명": rule_name,
            "조건": criterion,
            "데이터 값": data_value,
            "해석 의미": interpretation,
            "Rule ID": rule_id,
        })

    company = cc.company_interpretation
    if company:
        for rule in company.detected_rules:
            if isinstance(rule, dict):
                rule_id = rule.get("ruleId") or rule.get("rule_id") or ""
                rule_name = rule.get("ruleName") or rule.get("rule_name") or rule_id
                pts = rule.get("matchedPoints") or rule.get("matched_points") or []
                vals = rule.get("matchedValues") or rule.get("matched_values") or []
                criterion = rule.get("condition") or _rule_condition(rule_id, rule.get("description", ""))
                interpretation = (
                    rule.get("interpretationMeaning")
                    or rule.get("interpretation")
                    or _rule_interpretation(rule_id)
                )
            else:
                rule_id = getattr(rule, "rule_id", "")
                rule_name = getattr(rule, "rule_name", rule_id)
                pts = getattr(rule, "matched_points", [])
                vals = getattr(rule, "matched_values", [])
                criterion = getattr(rule, "condition", "") or _rule_condition(rule_id)
                interpretation = getattr(rule, "interpretation_meaning", "") or _rule_interpretation(rule_id)

            val_by_point = dict(zip(pts, vals)) if len(vals) == len(pts) else {}
            for p in pts:
                v = val_by_point.get(p)
                append(
                    int(p),
                    rule_name,
                    criterion,
                    interpretation,
                    f"{v:.4f}" if v is not None else "",
                    rule_id,
                )

    for pat in cc.detected_patterns:
        criterion = pat.description or pat.pattern_name_ko
        for p in pat.affected_points:
            append(int(p), pat.pattern_name_ko, criterion, pat.description)

    if not rows:
        return pd.DataFrame(
            columns=[point_label, "규칙명", "조건", "데이터 값", "해석 의미", "Rule ID"]
        )

    df = pd.DataFrame(rows)
    df[point_label] = pd.to_numeric(df[point_label], errors="coerce")
    return df.sort_values(point_label).reset_index(drop=True)


def summarize_anomaly_points(decision: SpcDecisionResult) -> set[int]:
    """표에 포함된 고유 포인트 번호."""
    cc = decision.control_chart
    pts: set[int] = set()
    company = cc.company_interpretation
    if company:
        for rule in company.detected_rules:
            raw = rule.get("matchedPoints") or rule.get("matched_points") if isinstance(rule, dict) else rule.matched_points
            if raw:
                pts.update(int(p) for p in raw)
    for pat in cc.detected_patterns:
        pts.update(int(p) for p in pat.affected_points)
    return pts
