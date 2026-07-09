"""Western Electric Rules (AIAG-VDA) — 관리도 이상 패턴 감지."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.spc.decision_models import DetectedPattern
from src.spc.pattern_catalog import get_pattern_meta


@dataclass
class WesternElectricViolation:
    """단일 WE 규칙 위반 요약."""

    rule_id: str
    rule_name: str
    occurrence_count: int
    affected_subgroups: list[int] = field(default_factory=list)
    windows: list[list[int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "occurrence_count": self.occurrence_count,
            "affected_subgroups": self.affected_subgroups,
            "windows": self.windows,
        }


def _meta_pattern(pattern_id: str, points: list[int]) -> DetectedPattern:
    meta = get_pattern_meta(pattern_id)
    if meta is None:
        raise KeyError(pattern_id)
    return DetectedPattern(
        pattern_id=meta.pattern_id,
        pattern_name_ko=meta.pattern_name_ko,
        description=meta.description,
        likely_causes=list(meta.likely_causes),
        recommended_actions=list(meta.recommended_actions),
        severity=meta.severity,
        affected_points=points,
    )


def _sigma_zones(cl: float, ucl: float, lcl: float) -> tuple[float, float, float, float]:
    """CL 기준 1σ·2σ 상·하한."""
    sigma = (ucl - cl) / 3.0 if ucl != lcl else 0.0
    return cl + sigma, cl - sigma, cl + 2 * sigma, cl - 2 * sigma


def detect_western_electric_rules(
    values: np.ndarray,
    cl: float,
    ucl: float,
    lcl: float,
    point_ids: list[int],
    *,
    run_points: int = 7,
    trend_points: int = 7,
) -> tuple[list[WesternElectricViolation], list[DetectedPattern]]:
    """
    Western Electric Rules 1~5 전체 적용.

    Returns:
        violations: 규칙별 위반 요약 (ID, 횟수, subgroup 번호)
        patterns: DetectedPattern 목록 (rule_engine 연동)
    """
    n = len(values)
    violations: list[WesternElectricViolation] = []
    patterns: list[DetectedPattern] = []
    if n == 0 or ucl == lcl:
        return violations, patterns

    one_up, one_lo, two_up, two_lo = _sigma_zones(cl, ucl, lcl)

    # Rule 1: 1 point beyond 3σ
    r1_idx = [i for i, v in enumerate(values) if v > ucl or v < lcl]
    if r1_idx:
        pts = sorted({point_ids[i] for i in r1_idx})
        violations.append(WesternElectricViolation(
            rule_id="WE_R1",
            rule_name="Rule 1: 1 point beyond 3σ",
            occurrence_count=len(r1_idx),
            affected_subgroups=pts,
            windows=[[point_ids[i]] for i in r1_idx],
        ))
        patterns.append(_meta_pattern("we_rule_1", pts))

    # Rule 2: 2 of 3 consecutive beyond 2σ (same side)
    r2_windows: list[list[int]] = []
    for start in range(n - 2):
        seg = values[start : start + 3]
        ids = point_ids[start : start + 3]
        above = int(np.sum(seg > two_up))
        below = int(np.sum(seg < two_lo))
        if above >= 2 or below >= 2:
            r2_windows.append(list(ids))
    if r2_windows:
        pts = sorted({p for w in r2_windows for p in w})
        violations.append(WesternElectricViolation(
            rule_id="WE_R2",
            rule_name="Rule 2: 2 of 3 consecutive beyond 2σ",
            occurrence_count=len(r2_windows),
            affected_subgroups=pts,
            windows=r2_windows,
        ))
        patterns.append(_meta_pattern("we_rule_2", pts))

    # Rule 3: 4 of 5 consecutive beyond 1σ (same side)
    r3_windows: list[list[int]] = []
    for start in range(n - 4):
        seg = values[start : start + 5]
        ids = point_ids[start : start + 5]
        above = int(np.sum(seg > one_up))
        below = int(np.sum(seg < one_lo))
        if above >= 4 or below >= 4:
            r3_windows.append(list(ids))
    if r3_windows:
        pts = sorted({p for w in r3_windows for p in w})
        violations.append(WesternElectricViolation(
            rule_id="WE_R3",
            rule_name="Rule 3: 4 of 5 consecutive beyond 1σ",
            occurrence_count=len(r3_windows),
            affected_subgroups=pts,
            windows=r3_windows,
        ))
        patterns.append(_meta_pattern("we_rule_3", pts))

    # Rule 4: N consecutive on one side of center
    r4_windows: list[list[int]] = []
    if n >= run_points:
        for start in range(n - run_points + 1):
            seg = values[start : start + run_points]
            if np.all(seg > cl) or np.all(seg < cl):
                r4_windows.append(point_ids[start : start + run_points])
    if r4_windows:
        pts = sorted({p for w in r4_windows for p in w})
        violations.append(WesternElectricViolation(
            rule_id="WE_R4",
            rule_name=f"Rule 4: {run_points} consecutive on one side of center",
            occurrence_count=len(r4_windows),
            affected_subgroups=pts,
            windows=r4_windows,
        ))
        patterns.append(_meta_pattern("we_rule_4", pts))

    # Rule 5: N consecutive increasing or decreasing
    r5_windows: list[list[int]] = []
    if n >= trend_points:
        for start in range(n - trend_points + 1):
            seg = values[start : start + trend_points]
            diffs = np.diff(seg)
            if np.all(diffs > 0) or np.all(diffs < 0):
                r5_windows.append(point_ids[start : start + trend_points])
    if r5_windows:
        pts = sorted({p for w in r5_windows for p in w})
        violations.append(WesternElectricViolation(
            rule_id="WE_R5",
            rule_name=f"Rule 5: {trend_points} consecutive increasing/decreasing",
            occurrence_count=len(r5_windows),
            affected_subgroups=pts,
            windows=r5_windows,
        ))
        patterns.append(_meta_pattern("we_rule_5", pts))

    return violations, patterns


def format_we_summary(violations: list[WesternElectricViolation]) -> str:
    """관리도 이상 패턴 요약 문자열."""
    if not violations:
        return "Western Electric Rules: 위반 없음"
    parts = []
    for v in violations:
        loc = ", ".join(str(p) for p in v.affected_subgroups[:8])
        if len(v.affected_subgroups) > 8:
            loc += "..."
        parts.append(f"{v.rule_id} ({v.occurrence_count}회, subgroup {loc})")
    return "; ".join(parts)
