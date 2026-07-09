"""측정값 극단치 탐지 — spec 대비 0·상한 초과 등 (정규성·관리도 전 사전 점검)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# spec 한계 대비 '현저히' 벗어난 정도 (공차 폭의 비율)
BEYOND_SPEC_WIDTH_RATIO = 0.5

# 규격 한계 절대값이 이 이하면 '0 근처 spec' (value=0 정상)
SPEC_NEAR_ZERO_ABS = 0.05


@dataclass
class ValueExtremePoint:
    row_index: int
    value: float
    reason: str
    reason_code: str


@dataclass
class ValueExtremeReport:
    points: list[ValueExtremePoint] = field(default_factory=list)
    spec_near_zero: bool = False
    usl: float | None = None
    lsl: float | None = None

    @property
    def has_extremes(self) -> bool:
        return len(self.points) > 0

    @property
    def row_indices(self) -> list[int]:
        return [p.row_index for p in self.points]


def _value_array(df: pd.DataFrame) -> tuple[pd.Series, np.ndarray]:
    if "value" not in df.columns:
        return pd.Series(dtype=float), np.array([])
    series = pd.to_numeric(df["value"], errors="coerce")
    return series, series.dropna().to_numpy(dtype=float)


def spec_near_zero(
    usl: float | None,
    lsl: float | None,
    values: np.ndarray,
) -> bool:
    """
    규격 한계 자체가 0에 가깝다면 value=0 은 정상으로 본다.
    (예: -0.02~0.02 mm 편차 측정 — 0은 유효값)
    """
    refs = [x for x in (lsl, usl) if x is not None]
    if not refs:
        return False
    max_abs = max(abs(r) for r in refs)
    if max_abs <= SPEC_NEAR_ZERO_ABS:
        return True
    if lsl is not None and usl is not None:
        width = usl - lsl
        if width > 0:
            mid = abs((usl + lsl) / 2)
            if mid <= width * 0.25 and max_abs <= width * 1.5:
                return True
    return False


def _spec_width(usl: float | None, lsl: float | None) -> float | None:
    if usl is not None and lsl is not None and usl > lsl:
        return usl - lsl
    if usl is not None:
        return abs(usl)
    if lsl is not None:
        return abs(lsl)
    return None


def _significantly_above_usl(value: float, usl: float | None, lsl: float | None) -> bool:
    if usl is None:
        return False
    width = _spec_width(usl, lsl)
    if width is not None and width > 0:
        margin = width * BEYOND_SPEC_WIDTH_RATIO
        return value > usl + margin
    if usl > 0:
        return value > usl * (1.0 + BEYOND_SPEC_WIDTH_RATIO)
    return value > usl + max(abs(usl) * BEYOND_SPEC_WIDTH_RATIO, 1e-6)


def _significantly_below_lsl(value: float, usl: float | None, lsl: float | None) -> bool:
    if lsl is None:
        return False
    width = _spec_width(usl, lsl)
    if width is not None and width > 0:
        margin = width * BEYOND_SPEC_WIDTH_RATIO
        return value < lsl - margin
    if lsl > 0:
        return value < lsl * (1.0 - BEYOND_SPEC_WIDTH_RATIO)
    return value < lsl - max(abs(lsl) * BEYOND_SPEC_WIDTH_RATIO, 1e-6)


def _is_zero_value(value: float, *, atol: float = 1e-12) -> bool:
    return abs(value) <= atol


def detect_value_extremes(
    df: pd.DataFrame,
    *,
    usl: float | None = None,
    lsl: float | None = None,
) -> ValueExtremeReport:
    """
    측정값이 극단치인 행 탐지.

    - value ≈ 0 이고 규격이 0 근처가 아니면 이상 (결측·미측정 placeholder)
    - USL/LSL 대비 현저히 벗어난 값
    """
    report = ValueExtremeReport(usl=usl, lsl=lsl)
    if df is None or df.empty or "value" not in df.columns:
        return report

    series, values = _value_array(df)
    if len(values) == 0:
        return report

    report.spec_near_zero = spec_near_zero(usl, lsl, values)

    for idx, raw in series.items():
        if pd.isna(raw):
            continue
        val = float(raw)
        if not report.spec_near_zero and _is_zero_value(val):
            report.points.append(
                ValueExtremePoint(
                    row_index=int(idx),
                    value=val,
                    reason_code="ZERO_VALUE",
                    reason="측정값 0 — 규격이 0 근처가 아니어서 결측·미측정 placeholder 가능",
                )
            )
            continue
        if _significantly_above_usl(val, usl, lsl):
            report.points.append(
                ValueExtremePoint(
                    row_index=int(idx),
                    value=val,
                    reason_code="ABOVE_USL",
                    reason=f"USL({usl:g}) 대비 현저히 높음",
                )
            )
            continue
        if _significantly_below_lsl(val, usl, lsl):
            report.points.append(
                ValueExtremePoint(
                    row_index=int(idx),
                    value=val,
                    reason_code="BELOW_LSL",
                    reason=f"LSL({lsl:g}) 대비 현저히 낮음",
                )
            )

    return report


def filter_sample_excluding_extremes(
    sample_df: pd.DataFrame,
    exclude_indices: list[int] | set[int],
    *,
    subgroup_size: int | None = None,
) -> pd.DataFrame:
    """극단치 행 제거 — X-bar 계열은 불완전 subgroup 제거."""
    if sample_df is None or sample_df.empty:
        return sample_df
    exclude = set(int(i) for i in exclude_indices)
    out = sample_df.drop(index=list(exclude), errors="ignore").copy()
    if (
        subgroup_size
        and subgroup_size > 1
        and "subgroup_id" in out.columns
    ):
        counts = out.groupby("subgroup_id").size()
        valid = counts[counts == subgroup_size].index
        out = out[out["subgroup_id"].isin(valid)].copy()
    return out.reset_index(drop=True)
