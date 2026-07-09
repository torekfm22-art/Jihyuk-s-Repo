"""관리도 σ 1·2·3 구간선 — CL 기준, UCL/LCL 거리 절대값으로 σ 폭 산정."""
from __future__ import annotations

from typing import Iterator


def sigma_zone_widths(cl: float, ucl: float, lcl: float) -> tuple[float, float]:
    """상·하한 각각 CL까지 거리의 1/3 = 1σ 폭 (절대값)."""
    sigma_up = abs(ucl - cl) / 3.0
    sigma_lo = abs(cl - lcl) / 3.0
    return sigma_up, sigma_lo


def iter_sigma_zone_lines(
    cl: float,
    ucl: float,
    lcl: float,
    *,
    skip_coincident_with_limits: bool = True,
) -> Iterator[tuple[float, str]]:
    """(y값, 라벨) — +1σ~+3σ, -1σ~-3σ. ±3σ는 UCL/LCL과 겹치면 생략 가능."""
    sigma_up, sigma_lo = sigma_zone_widths(cl, ucl, lcl)
    if sigma_up < 1e-15 and sigma_lo < 1e-15:
        return

    span = max(abs(ucl - cl), abs(cl - lcl), 1e-12)
    tol = span * 1e-6

    for k in (1, 2, 3):
        y_plus = cl + k * sigma_up
        if not skip_coincident_with_limits or k < 3 or abs(y_plus - ucl) > tol:
            yield y_plus, f"+{k}σ"

        y_minus = cl - k * sigma_lo
        if y_minus < lcl - tol:
            continue
        if not skip_coincident_with_limits or k < 3 or abs(y_minus - lcl) > tol:
            yield y_minus, f"-{k}σ"
