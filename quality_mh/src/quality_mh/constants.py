"""확정 상수 및 상태값 정의."""
from __future__ import annotations

from enum import Enum


class RuleStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    RULE_NOT_CONFIRMED = "RULE_NOT_CONFIRMED"
    MANUAL_CONFIRM_REQUIRED = "MANUAL_CONFIRM_REQUIRED"
    SOURCE_NOT_VERIFIED = "SOURCE_NOT_VERIFIED"


class ValidationStatus(str, Enum):
    OK = "OK"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    RULE_NOT_CONFIRMED = "RULE_NOT_CONFIRMED"
    MANUAL_CONFIRM_REQUIRED = "MANUAL_CONFIRM_REQUIRED"
    SOURCE_NOT_VERIFIED = "SOURCE_NOT_VERIFIED"
    SKIPPED = "SKIPPED"


# 사용자 명세에서 확인된 상수만 포함
CONFIRMED_STEP_LENGTH_M = 0.6
CONFIRMED_MOD_TO_MINUTES = 0.129

DOMAINS = ("입고", "공정", "완성", "시험", "공통")

INSPECTION_TYPES = (
    "샘플링",
    "전수",
    "무검사",
    "순회검사",
    "순회검사(토크,하드웨어혼입)",
    "완성품외관",
    "외주품",
    "3차원",
)

FILE_ROLES = (
    "종합분석",
    "입고상세",
    "공정상세",
    "완성상세",
    "모답스동작분석",
    "원본이력",
    "미분류",
)

FACTORY_PATTERNS = {
    "김천": ["김천", "gimcheon", "gc"],
    "충주": ["충주", "chungju", "cj"],
    "천안": ["천안", "cheonan", "ca"],
    "평택": ["평택", "pyeongtaek", "pt"],
}
