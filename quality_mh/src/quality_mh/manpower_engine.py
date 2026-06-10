"""표준 인원 환산 엔진."""
from __future__ import annotations

import pandas as pd

from quality_mh.audit_engine import AuditEngine
from quality_mh.constants import RuleStatus, ValidationStatus
from quality_mh.models import ManpowerResult
from quality_mh.rule_loader import load_manpower_rules


class ManpowerEngine:
    def __init__(self, audit: AuditEngine | None = None) -> None:
        self.audit = audit or AuditEngine()
        self.rules = load_manpower_rules()
        self._rule_map = {r.rule_id: r for r in self.rules}

    def calc_headcount(self, total_mh: float, factory: str = "", line: str = "") -> ManpowerResult:
        rule = self._rule_map.get("MP-HEADCOUNT-BASE")
        annual_minutes = rule.parameters.get("annual_work_minutes") if rule else "RULE_NOT_CONFIRMED"
        utilization = rule.parameters.get("utilization_rate") if rule else "RULE_NOT_CONFIRMED"

        if annual_minutes == "RULE_NOT_CONFIRMED" or utilization == "RULE_NOT_CONFIRMED":
            self.audit.log_rule_application(
                "manpower_engine",
                "MP-HEADCOUNT-BASE",
                status=RuleStatus.RULE_NOT_CONFIRMED,
                message="인원 환산 분모 미확정",
            )
            return ManpowerResult(
                factory_name=factory,
                line_name=line,
                total_mh=total_mh,
                manpower_formula=rule.formula_expression if rule else "",
                standard_headcount=None,
                status=RuleStatus.RULE_NOT_CONFIRMED,
                message="annual_work_minutes / utilization_rate 미확정 - placeholder",
            )

        denominator = float(annual_minutes) * float(utilization)
        headcount = total_mh / denominator if denominator else None

        return ManpowerResult(
            factory_name=factory,
            line_name=line,
            total_mh=total_mh,
            manpower_formula=rule.formula_expression if rule else "",
            standard_headcount=headcount,
            status=RuleStatus.CONFIRMED,
            message="",
        )

    def calc_from_line_aggregate(self, line_agg_df: pd.DataFrame) -> pd.DataFrame:
        results = []
        for _, row in line_agg_df.iterrows():
            total_mh = row.get("total_mh")
            if pd.isna(total_mh):
                continue
            mp = self.calc_headcount(
                float(total_mh),
                factory=str(row.get("factory_name", "")),
                line=str(row.get("line_name", "")),
            )
            results.append(mp.model_dump())
        return pd.DataFrame(results)

    def summarize_by_factory(self, line_agg_df: pd.DataFrame) -> pd.DataFrame:
        if line_agg_df.empty:
            return pd.DataFrame()
        summary = line_agg_df.groupby("factory_name", dropna=False)["total_mh"].sum().reset_index()
        rows = []
        for _, row in summary.iterrows():
            mp = self.calc_headcount(float(row["total_mh"]), factory=str(row["factory_name"]))
            rows.append({
                "factory_name": row["factory_name"],
                "total_mh": row["total_mh"],
                "standard_headcount": mp.standard_headcount,
                "status": mp.status.value,
                "message": mp.message,
            })
        return pd.DataFrame(rows)
