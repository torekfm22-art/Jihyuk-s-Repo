"""파일 역할 및 공장 자동 분류."""
from __future__ import annotations

import re
from pathlib import Path

from quality_mh.constants import FACTORY_PATTERNS, FILE_ROLES, ValidationStatus
from quality_mh.models import FileAnalysisResult
from quality_mh.rule_loader import load_column_mapping


def detect_factory(file_name: str) -> str:
    lowered = file_name.lower()
    for factory, patterns in FACTORY_PATTERNS.items():
        for p in patterns:
            if p.lower() in lowered:
                return factory
    return ""


def detect_file_role(file_name: str, sheet_names: list[str]) -> str:
    mapping = load_column_mapping()
    hints = mapping.get("sheet_role_hints", {})
    combined = f"{file_name} {' '.join(sheet_names)}".lower()

    scores: dict[str, int] = {role: 0 for role in FILE_ROLES}
    for role, keywords in hints.items():
        for kw in keywords:
            if kw.lower() in combined:
                scores[role] = scores.get(role, 0) + 1

    best_role = max(scores, key=scores.get)
    if scores[best_role] == 0:
        return "미분류"
    return best_role


def classify_excel_file(path: Path, sheet_names: list[str]) -> FileAnalysisResult:
    factory = detect_factory(path.name)
    role = detect_file_role(path.name, sheet_names)
    status = ValidationStatus.OK if role != "미분류" else ValidationStatus.NEEDS_REVIEW
    message = "자동 분류 완료" if role != "미분류" else "파일 역할 수동 확인 필요"
    if not factory:
        status = ValidationStatus.NEEDS_REVIEW
        message = "공장명 미인식 - 수동 확인 필요"

    return FileAnalysisResult(
        file_name=path.name,
        factory_name=factory,
        file_role=role,
        sheet_names=sheet_names,
        status=status,
        message=message,
    )


def normalize_sheet_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name).strip())
