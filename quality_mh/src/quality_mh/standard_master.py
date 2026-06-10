"""표준 PPT 기반 업무 체계 관리."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from quality_mh.audit_engine import AuditEngine
from quality_mh.constants import RuleStatus
from quality_mh.models import StandardTask
from quality_mh.rule_loader import load_standard_tasks


class StandardMasterService:
    def __init__(self, path: Path | None = None, audit: AuditEngine | None = None) -> None:
        self.audit = audit or AuditEngine()
        self.tasks: list[StandardTask] = load_standard_tasks(path)
        for task in self.tasks:
            self.audit.log_rule_application(
                "standard_master",
                task.standard_id,
                action="load",
                status=RuleStatus(task.status.value) if isinstance(task.status, RuleStatus) else RuleStatus(task.status),
                message=task.description,
            )

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([t.model_dump() for t in self.tasks])

    def get_by_domain(self, domain: str) -> list[StandardTask]:
        return [t for t in self.tasks if t.major_category == domain]

    def get_quantitative_tasks(self) -> list[StandardTask]:
        return [t for t in self.tasks if t.task_type == "정량"]
