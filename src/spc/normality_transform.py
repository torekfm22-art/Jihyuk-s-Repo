"""정규성 미충족 시 Box-Cox · Johnson 변환 후 공정능력 재평가."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from scipy import stats

from src.spc.statistics import CapabilityResult, NormalityResult, SpcAnalyzer

TransformMethod = Literal["none", "box_cox", "johnson_su"]


@dataclass
class NormalityTransformResult:
    applied: bool
    method: TransformMethod
    normality_before: NormalityResult | None = None
    normality_after: NormalityResult | None = None
    transformed_data: np.ndarray | None = None
    transformed_usl: float | None = None
    transformed_lsl: float | None = None
    capability: CapabilityResult | None = None
    lambda_: float | None = None
    shift: float = 0.0
    johnson_params: tuple[float, ...] | None = None
    notes: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "method": self.method,
            "lambda": self.lambda_,
            "shift": self.shift,
            "johnson_params": list(self.johnson_params) if self.johnson_params else None,
            "p_value_before": self.normality_before.p_value if self.normality_before else None,
            "p_value_after": self.normality_after.p_value if self.normality_after else None,
            "notes": self.notes,
            "attempts": self.attempts,
            "capability": {
                "cp": self.capability.cp,
                "cpk": self.capability.cpk,
                "pp": self.capability.pp,
                "ppk": self.capability.ppk,
            }
            if self.capability
            else None,
        }


def _clean(data: np.ndarray) -> np.ndarray:
    return np.asarray(data, dtype=float)[~np.isnan(np.asarray(data, dtype=float))]


def _boxcox_forward(x: np.ndarray, lam: float) -> np.ndarray:
    if abs(lam) < 1e-8:
        return np.log(x)
    return (np.power(x, lam) - 1.0) / lam


def _johnson_forward(data: np.ndarray, params: tuple[float, ...]) -> np.ndarray:
    cdf = stats.johnsonsu.cdf(data, *params)
    cdf = np.clip(cdf, 1e-6, 1.0 - 1e-6)
    return stats.norm.ppf(cdf)


def _transform_spec_boxcox(
    usl: float | None,
    lsl: float | None,
    lam: float,
    shift: float,
) -> tuple[float | None, float | None]:
    usl_t: float | None = None
    lsl_t: float | None = None
    if usl is not None:
        usl_t = float(_boxcox_forward(np.array([usl + shift]), lam)[0])
    if lsl is not None:
        lsl_t = float(_boxcox_forward(np.array([lsl + shift]), lam)[0])
    if usl_t is not None and lsl_t is not None and usl_t <= lsl_t:
        return None, None
    return usl_t, lsl_t


def _transform_spec_johnson(
    usl: float | None,
    lsl: float | None,
    params: tuple[float, ...],
) -> tuple[float | None, float | None]:
    usl_t: float | None = None
    lsl_t: float | None = None
    if usl is not None:
        usl_t = float(_johnson_forward(np.array([usl]), params)[0])
    if lsl is not None:
        lsl_t = float(_johnson_forward(np.array([lsl]), params)[0])
    if usl_t is not None and lsl_t is not None and usl_t < lsl_t:
        usl_t, lsl_t = lsl_t, usl_t
    return usl_t, lsl_t


def _spec_limits_transformable(usl: float | None, lsl: float | None, shift: float) -> bool:
    if usl is None and lsl is None:
        return False
    if usl is not None and usl + shift <= 0:
        return False
    if lsl is not None and lsl + shift <= 0:
        return False
    return True


def sigma_within_transformed(
    transformed: np.ndarray,
    *,
    chart_type: str,
    subgroup_size: int | None,
    analyzer: SpcAnalyzer | None = None,
) -> float:
    """변환 데이터 기준 σ_within (subgroup 구조 반영)."""
    analyzer = analyzer or SpcAnalyzer()
    arr = _clean(transformed)
    if len(arr) < 2:
        return 0.0

    sg = subgroup_size or 1
    if sg > 1 and chart_type in ("xbar_r", "xbar_s") and len(arr) >= sg * 2:
        n_groups = len(arr) // sg
        sub = arr[: n_groups * sg].reshape(n_groups, sg)
        limits = (
            analyzer.xbar_r_limits(sub)
            if chart_type == "xbar_r"
            else analyzer.xbar_s_limits(sub)
        )
        return float(limits.sigma_estimate)

    limits = analyzer.imr_limits(arr)
    return float(limits.sigma_estimate)


def capability_on_transformed(
    transformed: np.ndarray,
    usl_t: float | None,
    lsl_t: float | None,
    *,
    chart_type: str,
    subgroup_size: int | None,
    analyzer: SpcAnalyzer | None = None,
) -> CapabilityResult:
    analyzer = analyzer or SpcAnalyzer()
    arr = _clean(transformed)
    sigma_w = sigma_within_transformed(
        arr, chart_type=chart_type, subgroup_size=subgroup_size, analyzer=analyzer
    )
    return analyzer.capability(arr, usl_t, lsl_t, sigma_w)


def try_box_cox_transform(
    data: np.ndarray,
    usl: float | None,
    lsl: float | None,
    *,
    alpha: float = 0.05,
) -> NormalityTransformResult | None:
    """Box-Cox 변환 시도 — 정규성 확보 시 변환 공간 Cp/Cpk 산출."""
    arr = _clean(data)
    analyzer = SpcAnalyzer(alpha=alpha)
    norm_before = analyzer.test_normality(arr)
    if norm_before.is_normal:
        return None
    if usl is None and lsl is None:
        return None

    shift = 0.0
    min_val = float(np.min(arr))
    if min_val <= 0:
        shift = abs(min_val) + 1e-3
    shifted = arr + shift
    if not _spec_limits_transformable(usl, lsl, shift):
        return None

    try:
        transformed, lam = stats.boxcox(shifted)
        norm_after = analyzer.test_normality(transformed)
        usl_t, lsl_t = _transform_spec_boxcox(usl, lsl, float(lam), shift)
        if usl_t is None and lsl_t is None:
            return None
        cap = capability_on_transformed(
            transformed, usl_t, lsl_t, chart_type="imr", subgroup_size=1, analyzer=analyzer
        )
        return NormalityTransformResult(
            applied=norm_after.is_normal,
            method="box_cox",
            normality_before=norm_before,
            normality_after=norm_after,
            transformed_data=transformed,
            transformed_usl=usl_t,
            transformed_lsl=lsl_t,
            capability=cap,
            lambda_=float(lam),
            shift=shift,
            notes=(
                f"Box-Cox λ={lam:.4f}, shift={shift:.4g} → "
                f"p={norm_after.p_value:.4f} ({'정규' if norm_after.is_normal else '비정규'})"
            ),
        )
    except Exception:
        return None


def try_johnson_transform(
    data: np.ndarray,
    usl: float | None,
    lsl: float | None,
    *,
    alpha: float = 0.05,
    min_n: int = 8,
) -> NormalityTransformResult | None:
    """Johnson SU (johnsonsu 적합 + 정규 분위수 변환) 후 공정능력 산출."""
    arr = _clean(data)
    if len(arr) < min_n:
        return None
    if usl is None and lsl is None:
        return None

    analyzer = SpcAnalyzer(alpha=alpha)
    norm_before = analyzer.test_normality(arr)
    if norm_before.is_normal:
        return None

    try:
        params = stats.johnsonsu.fit(arr)
        transformed = _johnson_forward(arr, params)
        if not np.all(np.isfinite(transformed)):
            return None
        norm_after = analyzer.test_normality(transformed)
        usl_t, lsl_t = _transform_spec_johnson(usl, lsl, params)
        if usl_t is None and lsl_t is None:
            return None
        cap = capability_on_transformed(
            transformed, usl_t, lsl_t, chart_type="imr", subgroup_size=1, analyzer=analyzer
        )
        return NormalityTransformResult(
            applied=norm_after.is_normal,
            method="johnson_su",
            normality_before=norm_before,
            normality_after=norm_after,
            transformed_data=transformed,
            transformed_usl=usl_t,
            transformed_lsl=lsl_t,
            capability=cap,
            johnson_params=tuple(float(p) for p in params),
            notes=(
                f"Johnson SU → p={norm_after.p_value:.4f} "
                f"({'정규' if norm_after.is_normal else '비정규'})"
            ),
            detail={"johnson_a": params[0], "johnson_b": params[1], "loc": params[2], "scale": params[3]},
        )
    except Exception:
        return None


def _attempt_record(
    result: NormalityTransformResult | None,
    *,
    method: TransformMethod,
    method_label: str,
) -> dict[str, Any]:
    if result is None:
        return {
            "method": method,
            "method_label": method_label,
            "attempted": False,
            "p_value_after": None,
            "statistic_after": None,
            "is_normal_after": None,
            "success": False,
            "selected": False,
            "lambda": None,
            "shift": None,
            "notes": "변환 시도 불가 (데이터·규격 조건 미충족)",
        }
    after = result.normality_after
    return {
        "method": method,
        "method_label": method_label,
        "attempted": True,
        "p_value_after": after.p_value if after else None,
        "statistic_after": after.statistic if after else None,
        "is_normal_after": after.is_normal if after else False,
        "success": result.applied,
        "selected": False,
        "lambda": result.lambda_,
        "shift": result.shift if method == "box_cox" else None,
        "notes": result.notes,
    }


def resolve_normality_transform(
    data: np.ndarray,
    usl: float | None,
    lsl: float | None,
    *,
    chart_type: str = "xbar_s",
    subgroup_size: int | None = None,
    alpha: float = 0.05,
) -> NormalityTransformResult:
    """
    비정규 시 Box-Cox → Johnson 순으로 변환 시도.
    성공 시 subgroup 구조를 반영한 σ_within으로 Cp/Cpk 재산출.
    """
    arr = _clean(data)
    analyzer = SpcAnalyzer(alpha=alpha)
    norm_before = analyzer.test_normality(arr)

    if norm_before.is_normal:
        return NormalityTransformResult(
            applied=False,
            method="none",
            normality_before=norm_before,
            notes="원 데이터 정규성 충족 — 변환 불필요",
        )

    bc = try_box_cox_transform(arr, usl, lsl, alpha=alpha)
    jn = try_johnson_transform(arr, usl, lsl, alpha=alpha)
    attempts = [
        _attempt_record(bc, method="box_cox", method_label="Box-Cox"),
        _attempt_record(jn, method="johnson_su", method_label="Johnson SU"),
    ]
    candidates: list[NormalityTransformResult] = [c for c in (bc, jn) if c is not None]

    for cand in candidates:
        if not cand.applied or cand.transformed_data is None:
            continue
        if cand.transformed_usl is None and cand.transformed_lsl is None:
            continue
        sigma_w = sigma_within_transformed(
            cand.transformed_data,
            chart_type=chart_type,
            subgroup_size=subgroup_size,
            analyzer=analyzer,
        )
        cand.capability = analyzer.capability(
            cand.transformed_data,
            cand.transformed_usl,
            cand.transformed_lsl,
            sigma_w,
        )
        cand.applied = True
        cand.notes += (
            f" | Cpk={cand.capability.cpk:.3f}, Cp={cand.capability.cp:.3f} (변환 공간)"
        )
        for att in attempts:
            if att["method"] == cand.method:
                att["selected"] = True
        return NormalityTransformResult(
            applied=True,
            method=cand.method,
            normality_before=norm_before,
            normality_after=cand.normality_after,
            transformed_data=cand.transformed_data,
            transformed_usl=cand.transformed_usl,
            transformed_lsl=cand.transformed_lsl,
            capability=cand.capability,
            lambda_=cand.lambda_,
            shift=cand.shift,
            johnson_params=cand.johnson_params,
            notes=cand.notes,
            detail=cand.detail,
            attempts=attempts,
        )

    tried = ", ".join(c.method for c in candidates) or "없음"
    return NormalityTransformResult(
        applied=False,
        method="none",
        normality_before=norm_before,
        notes=f"Box-Cox·Johnson 변환 후에도 정규성 미충족 (시도: {tried}) → Non-normal capability 또는 Ppk 중심 평가",
        attempts=attempts,
    )
