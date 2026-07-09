"""관리도 해석 엔진 — config/control_chart_rules.json 기준 9 Rule."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from src.spc.control_chart_rules_catalog import load_process_state_labels, rule_by_id

StatusType = Literal["관리상태", "비관리상태"]


@dataclass
class SpcInterpretConfig:
    """JSON detection 파라미터와 동기화 (오버라이드용)."""
    oscillation_min_points: int = 14
    hugging_min_consecutive: int = 15
    shift_min_consecutive: int = 7
    trend_min_consecutive: int = 6
    excess_dispersion_min_consecutive: int = 8
    zone_rule_1_window: int = 3
    zone_rule_1_min_count: int = 2
    zone_rule_1_sigma: float = 2.0
    zone_rule_2_window: int = 5
    zone_rule_2_min_count: int = 4
    zone_rule_2_sigma: float = 1.0


def config_from_rules_catalog() -> SpcInterpretConfig:
    """JSON detection 파라미터 → SpcInterpretConfig."""
    from src.spc.control_chart_rules_catalog import load_control_chart_rules

    cfg = SpcInterpretConfig()
    for rule in load_control_chart_rules():
        det = rule.detection
        t = det.get("type")
        if t == "oscillation":
            cfg.oscillation_min_points = int(det.get("min_points", cfg.oscillation_min_points))
        elif t == "hugging":
            cfg.hugging_min_consecutive = int(det.get("min_consecutive", cfg.hugging_min_consecutive))
        elif t == "shift":
            if "min_consecutive" in det:
                cfg.shift_min_consecutive = int(det["min_consecutive"])
            elif "lengths" in det:
                cfg.shift_min_consecutive = int(min(det["lengths"]))
        elif t == "trend":
            cfg.trend_min_consecutive = int(det.get("min_consecutive", cfg.trend_min_consecutive))
        elif t == "excess_dispersion":
            cfg.excess_dispersion_min_consecutive = int(
                det.get("min_consecutive", cfg.excess_dispersion_min_consecutive)
            )
        elif t == "zone_rule_1":
            cfg.zone_rule_1_window = int(det.get("window", cfg.zone_rule_1_window))
            cfg.zone_rule_1_min_count = int(det.get("min_count", cfg.zone_rule_1_min_count))
            cfg.zone_rule_1_sigma = float(det.get("sigma_level", cfg.zone_rule_1_sigma))
        elif t == "zone_rule_2":
            cfg.zone_rule_2_window = int(det.get("window", cfg.zone_rule_2_window))
            cfg.zone_rule_2_min_count = int(det.get("min_count", cfg.zone_rule_2_min_count))
            cfg.zone_rule_2_sigma = float(det.get("sigma_level", cfg.zone_rule_2_sigma))
    return cfg


@dataclass
class DetectedCompanyRule:
    rule_id: str
    rule_name: str
    condition: str
    interpretation_meaning: str
    description: str = ""
    matched_points: list[int] = field(default_factory=list)
    matched_values: list[float] = field(default_factory=list)
    windows: list[list[int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ruleId": self.rule_id,
            "ruleName": self.rule_name,
            "condition": self.condition,
            "interpretation": self.interpretation_meaning,
            "interpretationMeaning": self.interpretation_meaning,
            "description": self.description or self.condition,
            "matchedPoints": self.matched_points,
            "matchedValues": self.matched_values,
            "windows": self.windows,
        }


@dataclass
class CompanyChartInterpretation:
    status: StatusType
    detected_rules: list[DetectedCompanyRule] = field(default_factory=list)
    summary_message: str = ""
    actions: list[str] = field(default_factory=list)
    mean_chart_deferred: bool = False
    dispersion_abnormal: bool = False

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "detectedRules": [r.to_dict() for r in self.detected_rules],
            "summaryMessage": self.summary_message,
            "actions": self.actions,
            "meanChartDeferred": self.mean_chart_deferred,
            "dispersionAbnormal": self.dispersion_abnormal,
        }


def _sigma_zones(cl: float, ucl: float, lcl: float) -> tuple[float, float, float, float]:
    sigma_up = (ucl - cl) / 3.0 if ucl != cl else 0.0
    sigma_lo = (cl - lcl) / 3.0 if lcl != cl else 0.0
    one_up = cl + sigma_up
    one_lo = cl - sigma_lo
    two_up = cl + 2 * sigma_up
    two_lo = cl - 2 * sigma_lo
    return one_up, one_lo, two_up, two_lo


def _make_rule(rule_id: str) -> DetectedCompanyRule | None:
    meta = rule_by_id(rule_id)
    if meta is None:
        return None
    return DetectedCompanyRule(
        rule_id=rule_id,
        rule_name=meta.rule_name,
        condition=meta.condition,
        interpretation_meaning=meta.interpretation,
        description=meta.condition,
    )


def _attach_points(
    rule: DetectedCompanyRule,
    values: np.ndarray,
    point_ids: list[int],
    indices: list[int],
    windows: list[list[int]] | None = None,
) -> DetectedCompanyRule:
    rule.matched_points = sorted({point_ids[i] for i in indices})
    rule.matched_values = [float(values[i]) for i in indices]
    if windows:
        rule.windows = windows
    return rule


def _check_spec_limits(
    values: np.ndarray,
    point_ids: list[int],
    usl: float | None,
    lsl: float | None,
) -> DetectedCompanyRule | None:
    if usl is None and lsl is None:
        return None
    idx: list[int] = []
    for i, v in enumerate(values):
        if usl is not None and v > usl:
            idx.append(i)
        elif lsl is not None and v < lsl:
            idx.append(i)
    if not idx:
        return None
    rule = _make_rule("SPEC_LIMIT_OUT")
    assert rule is not None
    return _attach_points(rule, values, point_ids, idx, [[point_ids[i]] for i in idx])


def _check_control_limits(
    values: np.ndarray, ucl: float, lcl: float, point_ids: list[int]
) -> DetectedCompanyRule | None:
    idx = [i for i, v in enumerate(values) if v > ucl or v < lcl]
    if not idx:
        return None
    rule = _make_rule("CONTROL_LIMIT_OUT")
    assert rule is not None
    return _attach_points(rule, values, point_ids, idx, [[point_ids[i]] for i in idx])


def _check_oscillation(
    values: np.ndarray, point_ids: list[int], min_points: int
) -> DetectedCompanyRule | None:
    n = len(values)
    if n < min_points:
        return None
    diffs = np.diff(values)
    best_start = None
    best_len = 0
    i = 0
    while i < len(diffs):
        run_start = i
        run_len = 1
        j = i + 1
        while j < len(diffs):
            if diffs[j] == 0 or diffs[j - 1] == 0:
                break
            if diffs[j] * diffs[j - 1] < 0:
                run_len += 1
                j += 1
            else:
                break
        if run_len >= min_points - 1 and run_len > best_len:
            best_len = run_len
            best_start = run_start
        i = max(i + 1, j)
    if best_start is None:
        return None
    end = best_start + best_len
    indices = list(range(best_start, end + 1))
    rule = _make_rule("OSCILLATION")
    assert rule is not None
    return _attach_points(rule, values, point_ids, indices, [point_ids[best_start : end + 1]])


def _beyond_sigma_mask(values: np.ndarray, cl: float, ucl: float, lcl: float, level: float, side: str) -> np.ndarray:
    one_up, one_lo, two_up, two_lo = _sigma_zones(cl, ucl, lcl)
    if level >= 2:
        upper, lower = two_up, two_lo
    else:
        upper, lower = one_up, one_lo
    if side == "above":
        return values > upper
    if side == "below":
        return values < lower
    return (values > upper) | (values < lower)


def _check_zone_rule(
    values: np.ndarray,
    cl: float,
    ucl: float,
    lcl: float,
    point_ids: list[int],
    *,
    rule_id: str,
    window: int,
    min_count: int,
    sigma_level: float,
) -> DetectedCompanyRule | None:
    n = len(values)
    if n < window:
        return None
    windows: list[list[int]] = []
    for start in range(n - window + 1):
        seg = values[start : start + window]
        ids = point_ids[start : start + window]
        above = int(np.sum(_beyond_sigma_mask(seg, cl, ucl, lcl, sigma_level, "above")))
        below = int(np.sum(_beyond_sigma_mask(seg, cl, ucl, lcl, sigma_level, "below")))
        if above >= min_count or below >= min_count:
            windows.append(list(ids))
    if not windows:
        return None
    rule = _make_rule(rule_id)
    assert rule is not None
    indices = sorted({i for w in windows for i, pid in enumerate(point_ids) if pid in w})
    flat_idx = [point_ids.index(p) for p in sorted({p for w in windows for p in w})]
    return _attach_points(rule, values, point_ids, flat_idx, windows)


def _check_hugging(
    values: np.ndarray, cl: float, ucl: float, lcl: float, point_ids: list[int], min_consecutive: int
) -> DetectedCompanyRule | None:
    one_up, one_lo, _, _ = _sigma_zones(cl, ucl, lcl)
    if one_up == one_lo:
        return None
    within = (values >= one_lo) & (values <= one_up)
    best_start = None
    best_len = 0
    run_start = 0
    run_len = 0
    for i, ok in enumerate(within):
        if ok:
            if run_len == 0:
                run_start = i
            run_len += 1
            if run_len >= min_consecutive and run_len > best_len:
                best_len = run_len
                best_start = run_start
        else:
            run_len = 0
    if best_start is None:
        return None
    indices = list(range(best_start, best_start + best_len))
    rule = _make_rule("HUGGING")
    assert rule is not None
    return _attach_points(rule, values, point_ids, indices, [point_ids[best_start : best_start + best_len]])


def _check_shift(
    values: np.ndarray, cl: float, point_ids: list[int], min_consecutive: int
) -> DetectedCompanyRule | None:
    if len(values) < min_consecutive:
        return None
    windows: list[list[int]] = []
    for start in range(len(values) - min_consecutive + 1):
        seg = values[start : start + min_consecutive]
        if np.all(seg > cl) or np.all(seg < cl):
            windows.append(point_ids[start : start + min_consecutive])
    if not windows:
        return None
    rule = _make_rule("SHIFT")
    assert rule is not None
    flat_idx = sorted({point_ids.index(p) for w in windows for p in w})
    return _attach_points(rule, values, point_ids, flat_idx, windows)


def _check_trend(
    values: np.ndarray, point_ids: list[int], min_consecutive: int
) -> DetectedCompanyRule | None:
    if len(values) < min_consecutive:
        return None
    windows: list[list[int]] = []
    for start in range(len(values) - min_consecutive + 1):
        seg = values[start : start + min_consecutive]
        diffs = np.diff(seg)
        if np.all(diffs > 0) or np.all(diffs < 0):
            windows.append(point_ids[start : start + min_consecutive])
    if not windows:
        return None
    rule = _make_rule("TREND")
    assert rule is not None
    flat_idx = sorted({point_ids.index(p) for w in windows for p in w})
    return _attach_points(rule, values, point_ids, flat_idx, windows)


def _check_excess_dispersion(
    values: np.ndarray, cl: float, ucl: float, lcl: float, point_ids: list[int], min_consecutive: int
) -> DetectedCompanyRule | None:
    one_up, one_lo, _, _ = _sigma_zones(cl, ucl, lcl)
    if one_up == one_lo:
        return None
    outside = (values > one_up) | (values < one_lo)
    best_start = None
    best_len = 0
    run_start = 0
    run_len = 0
    for i, out in enumerate(outside):
        if out:
            if run_len == 0:
                run_start = i
            run_len += 1
            if run_len >= min_consecutive and run_len > best_len:
                best_len = run_len
                best_start = run_start
        else:
            run_len = 0
    if best_start is None:
        return None
    indices = list(range(best_start, best_start + best_len))
    rule = _make_rule("EXCESS_DISPERSION")
    assert rule is not None
    return _attach_points(rule, values, point_ids, indices, [point_ids[best_start : best_start + best_len]])


def _build_actions(rules: list[DetectedCompanyRule], deferred: bool) -> list[str]:
    actions: list[str] = []
    if deferred:
        actions.append("산포관리도 이상 → 평균관리도 신뢰 불가 (참고용)")
    for r in rules:
        actions.append(f"{r.rule_name}: {r.interpretation_meaning}")
    labels = load_process_state_labels()
    if not rules and not deferred:
        actions.append(f"이상 신호 없음 — {labels['in_control_label']} 유지·정기 모니터링")
    return actions


def interpret_control_chart(
    values: np.ndarray,
    cl: float,
    ucl: float,
    lcl: float,
    point_ids: list[int],
    *,
    usl: float | None = None,
    lsl: float | None = None,
    config: SpcInterpretConfig | None = None,
    dispersion_abnormal: bool = False,
) -> CompanyChartInterpretation:
    """
    JSON 카탈로그 9 Rule 순서 평가.
    어떤 Rule이라도 만족 → 비관리상태, 없으면 관리상태.
    """
    cfg = config or config_from_rules_catalog()
    values = np.asarray(values, dtype=float)
    labels = load_process_state_labels()
    in_label = labels["in_control_label"]
    out_label = labels["out_of_control_label"]

    if len(values) == 0 or ucl == lcl:
        return CompanyChartInterpretation(
            status=in_label,  # type: ignore[arg-type]
            summary_message="데이터 부족 — 판정 보류",
            dispersion_abnormal=dispersion_abnormal,
        )

    detected: list[DetectedCompanyRule] = []
    checks = [
        lambda: _check_spec_limits(values, point_ids, usl, lsl),
        lambda: _check_control_limits(values, ucl, lcl, point_ids),
        lambda: _check_oscillation(values, point_ids, cfg.oscillation_min_points),
        lambda: _check_zone_rule(
            values, cl, ucl, lcl, point_ids,
            rule_id="ZONE_RULE_1",
            window=cfg.zone_rule_1_window,
            min_count=cfg.zone_rule_1_min_count,
            sigma_level=cfg.zone_rule_1_sigma,
        ),
        lambda: _check_hugging(values, cl, ucl, lcl, point_ids, cfg.hugging_min_consecutive),
        lambda: _check_shift(values, cl, point_ids, cfg.shift_min_consecutive),
        lambda: _check_trend(values, point_ids, cfg.trend_min_consecutive),
        lambda: _check_zone_rule(
            values, cl, ucl, lcl, point_ids,
            rule_id="ZONE_RULE_2",
            window=cfg.zone_rule_2_window,
            min_count=cfg.zone_rule_2_min_count,
            sigma_level=cfg.zone_rule_2_sigma,
        ),
        lambda: _check_excess_dispersion(
            values, cl, ucl, lcl, point_ids, cfg.excess_dispersion_min_consecutive
        ),
    ]
    for check in checks:
        hit = check()
        if hit:
            detected.append(hit)

    if detected:
        status: StatusType = out_label  # type: ignore[assignment]
        names = ", ".join(r.rule_name for r in detected)
        summary = f"{out_label} — {len(detected)}건 Rule 발생: {names}"
    else:
        status = in_label  # type: ignore[assignment]
        summary = f"{in_label} — 이상 신호 없음 (9 Rule 기준)"

    deferred = dispersion_abnormal
    if deferred and status == out_label:
        summary += " | 산포관리도 이상 → 평균관리도 참고용"

    return CompanyChartInterpretation(
        status=status,
        detected_rules=detected,
        summary_message=summary,
        actions=_build_actions(detected, deferred),
        mean_chart_deferred=deferred,
        dispersion_abnormal=dispersion_abnormal,
    )


def format_company_rules_summary(interp: CompanyChartInterpretation) -> str:
    if interp.status == load_process_state_labels()["in_control_label"]:
        return interp.summary_message
    parts = [f"{r.rule_name}({len(r.matched_points)}점)" for r in interp.detected_rules]
    return "관리도 Rule 발생: " + ", ".join(parts)
