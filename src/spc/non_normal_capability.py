"""비정규 데이터 공정능력 — percentile/Z-score 기반 Non-normal Cp/Cpk · Pp/Ppk."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy import stats


@dataclass
class NonNormalCapabilityResult:
    pp: float
    ppk: float
    cp: float
    cpk: float
    p_below_lsl: float
    p_above_usl: float
    spread_percentile: float
    method: str
    notes: str

    def to_dict(self) -> dict:
        return {
            "Pp_nn": round(self.pp, 4),
            "Ppk_nn": round(self.ppk, 4),
            "Cp_nn": round(self.cp, 4),
            "Cpk_nn": round(self.cpk, 4),
            "P_below_LSL": round(self.p_below_lsl, 6),
            "P_above_USL": round(self.p_above_usl, 6),
            "method": self.method,
        }


def _clamp_prob(p: float, n: int) -> float:
    eps = 0.5 / max(n, 1)
    return float(np.clip(p, eps, 1.0 - eps))


def percentile_capability(
    data: np.ndarray,
    usl: float | None = None,
    lsl: float | None = None,
    *,
    within_spread: float | None = None,
) -> NonNormalCapabilityResult:
    """
    Percentile 기반 비정규 공정능력 (Minitab Non-normal capability 유사).

    - spread: P99.865 − P0.135 (또는 within_spread 지정 시 σ_within×6)
    - Ppk/Pp: 경험적 규격 이탈 확률 → Z-score → /3
    """
    arr = np.asarray(data, dtype=float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 3:
        return NonNormalCapabilityResult(0, 0, 0, 0, 0, 0, 0, "percentile", "표본 부족")

    mean = float(np.mean(arr))
    p_below = float(np.mean(arr <= lsl)) if lsl is not None else 0.0
    p_above = float(np.mean(arr >= usl)) if usl is not None else 0.0

    z_lsl = abs(stats.norm.ppf(_clamp_prob(p_below, n))) if lsl is not None else 0.0
    z_usl = abs(stats.norm.ppf(_clamp_prob(p_above, n))) if usl is not None else 0.0
    if usl is not None and lsl is not None:
        ppk_z = min(z_lsl, z_usl)
        pp_z = (z_lsl + z_usl) / 2.0 if (z_lsl + z_usl) > 0 else 0.0
    elif usl is not None:
        ppk_z = z_usl
        pp_z = z_usl
    else:
        ppk_z = z_lsl
        pp_z = z_lsl

    if within_spread and within_spread > 0:
        spread = within_spread
        method = "percentile + σ_within"
    else:
        p_lo = float(np.percentile(arr, 0.135))
        p_hi = float(np.percentile(arr, 99.865))
        spread = p_hi - p_lo
        if spread <= 0:
            spread = float(np.std(arr, ddof=1)) * 6.0 or 1e-9
        method = "percentile (P0.135~P99.865)"

    half = spread / 2.0
    if usl is not None and lsl is not None:
        pp_pct = (usl - lsl) / spread if spread > 0 else 0.0
        ppk_pct = min((usl - mean) / half, (mean - lsl) / half) if half > 0 else 0.0
    elif usl is not None:
        pp_pct = float("nan")
        ppk_pct = (usl - mean) / half if half > 0 else 0.0
    else:
        pp_pct = float("nan")
        ppk_pct = (mean - lsl) / half if lsl is not None and half > 0 else 0.0

    pp_val = pp_z if math.isnan(pp_pct) else max(pp_z, pp_pct)
    return NonNormalCapabilityResult(
        pp=pp_val,
        ppk=ppk_z,
        cp=pp_pct,
        cpk=ppk_pct,
        p_below_lsl=p_below,
        p_above_usl=p_above,
        spread_percentile=spread,
        method=method,
        notes=f"경험적 P(X≤LSL)={p_below:.4%}, P(X≥USL)={p_above:.4%}",
    )
