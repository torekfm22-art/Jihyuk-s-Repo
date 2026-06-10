"""규칙 적용 및 출처 추적."""
from __future__ import annotations

from quality_mh.constants import RuleStatus, ValidationStatus
from quality_mh.models import AuditEntry, CalculationLog, MhResult


class AuditEngine:
    def __init__(self) -> None:
        self.audit_entries: list[AuditEntry] = []
        self.calculation_logs: list[CalculationLog] = []
        self.review_items: list[dict] = []

    def log_rule_application(
        self,
        engine: str,
        rule_id: str,
        *,
        source_file: str = "",
        source_sheet: str = "",
        source_range: str = "",
        action: str = "apply",
        status: RuleStatus | ValidationStatus = RuleStatus.NEEDS_REVIEW,
        message: str = "",
        detail: dict | None = None,
    ) -> None:
        entry = AuditEntry(
            engine=engine,
            rule_id=rule_id,
            source_file=source_file,
            source_sheet=source_sheet,
            source_range=source_range,
            action=action,
            status=status,
            message=message,
            detail=detail or {},
        )
        self.audit_entries.append(entry)
        if status in {
            RuleStatus.NEEDS_REVIEW,
            RuleStatus.RULE_NOT_CONFIRMED,
            RuleStatus.MANUAL_CONFIRM_REQUIRED,
            RuleStatus.SOURCE_NOT_VERIFIED,
            ValidationStatus.NEEDS_REVIEW,
            ValidationStatus.RULE_NOT_CONFIRMED,
            ValidationStatus.MANUAL_CONFIRM_REQUIRED,
            ValidationStatus.SOURCE_NOT_VERIFIED,
        }:
            self.review_items.append(
                {
                    "engine": engine,
                    "rule_id": rule_id,
                    "source_file": source_file,
                    "source_sheet": source_sheet,
                    "status": status.value if hasattr(status, "value") else str(status),
                    "message": message,
                }
            )

    def log_calculation(
        self,
        step: str,
        engine: str,
        *,
        input_summary: str = "",
        output_summary: str = "",
        rule_id: str = "",
        status: ValidationStatus = ValidationStatus.OK,
        message: str = "",
    ) -> None:
        self.calculation_logs.append(
            CalculationLog(
                step=step,
                engine=engine,
                input_summary=input_summary,
                output_summary=output_summary,
                rule_id=rule_id,
                status=status,
                message=message,
            )
        )

    def collect_review_from_mh(self, results: list[MhResult]) -> None:
        for r in results:
            if r.validation_status != ValidationStatus.OK:
                self.review_items.append(
                    {
                        "engine": "mh_engine",
                        "rule_id": f"{r.applied_frequency_rule}|{r.applied_unit_time_rule}",
                        "source_file": "",
                        "source_sheet": "",
                        "status": r.validation_status.value,
                        "message": f"{r.factory_name}/{r.domain}/{r.task_name}: {r.validation_message}",
                    }
                )

    def to_dataframes_dict(self):
        import pandas as pd

        return {
            "audit_entries": pd.DataFrame([e.model_dump() for e in self.audit_entries]),
            "calculation_logs": pd.DataFrame([c.model_dump() for c in self.calculation_logs]),
            "review_items": pd.DataFrame(self.review_items),
        }
