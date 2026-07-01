"""생산계획 연동 발생빈도 — FG expected qty.xlsx 수식 반영."""
from __future__ import annotations

from typing import Sequence


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def calc_inspection_production_ratio(
    monthly_inspection: Sequence[float],
    monthly_production: Sequence[float],
) -> list[float]:
    """월별 검사수량÷생산실적 비율 (FG row33: =C31/C32)."""
    return [
        _safe_div(float(ins), float(prod))
        for ins, prod in zip(monthly_inspection, monthly_production, strict=True)
    ]


def calc_average_ratio(ratios: Sequence[float], *, use_months: int | None = None) -> float:
    """유효 월 비율 평균 (FG: =AVERAGE(C33:J33) 등)."""
    values = [float(r) for r in ratios[: use_months or len(ratios)] if float(r) > 0]
    if not values:
        values = [float(r) for r in ratios if float(r) > 0]
    if not values:
        return 0.0
    return sum(values) / len(values)


def calc_product_inspection_shares(
    annual_inspection_by_product: dict[str, float],
) -> dict[str, float]:
    """유형별 검사비율(점유율) — 전년 검사수량 합계 대비."""
    total = sum(annual_inspection_by_product.values())
    if total <= 0:
        n = len(annual_inspection_by_product) or 1
        return {k: 1.0 / n for k in annual_inspection_by_product}
    return {k: v / total for k, v in annual_inspection_by_product.items()}


def calc_simple_plan_linked_frequency(
    prior_inspection_total: float,
    prior_production_total: float,
    forecast_production_total: float,
) -> tuple[float, dict, list[str]]:
    """단순 연동: (전년 검사합계÷전년 생산합계) × 당해년 생산계획."""
    log: list[str] = []
    log.append(f"[입력] 전년 검사수량 합계={prior_inspection_total}")
    log.append(f"[입력] 전년 생산실적 합계={prior_production_total}")
    log.append(f"[입력] 당해년 생산계획 합계={forecast_production_total}")
    ref_ratio = _safe_div(prior_inspection_total, prior_production_total)
    log.append(f"[공식] 기준비율 = 전년검사÷전년생산 = {ref_ratio:.6f}")
    frequency = ref_ratio * forecast_production_total
    log.append(f"[공식] 발생빈도(연간) = 기준비율 × 당해년생산 = {frequency:.2f}")
    factors = {
        "ref_ratio": ref_ratio,
        "prior_inspection_total": prior_inspection_total,
        "prior_production_total": prior_production_total,
        "plan_qty": forecast_production_total,
        "mode": "simple",
    }
    return frequency, factors, log


def calc_fg_style_plan_linked_frequency(
    *,
    prior_monthly_inspection_by_product: dict[str, list[float]],
    prior_monthly_production: Sequence[float],
    forecast_monthly_production: Sequence[float],
    ratio_months: int | None = None,
) -> tuple[float, dict, list[str]]:
    """
    FG expected qty 양식:
    - 전년 월별 유형별 검사수량 → 유형별 검사비율(점유율)
    - 전년 월별 검사합계÷생산실적 → 월별 비율의 평균
    - 당해년 월별: 월생산계획 × 평균비율 × 유형점유율 합산
    """
    log: list[str] = []
    months = 12
    prior_prod = [float(v) for v in prior_monthly_production[:months]]
    forecast_prod = [float(v) for v in forecast_monthly_production[:months]]

    # 전년 월별 검사 합계
    prior_monthly_total_inspection = [0.0] * months
    for product, monthly_vals in prior_monthly_inspection_by_product.items():
        vals = [float(v) for v in monthly_vals[:months]]
        log.append(f"[전년] {product} 연간검사={sum(vals):,.0f}")
        for i, v in enumerate(vals):
            prior_monthly_total_inspection[i] += v

    annual_by_product = {
        p: sum(float(v) for v in vals[:months])
        for p, vals in prior_monthly_inspection_by_product.items()
    }
    shares = calc_product_inspection_shares(annual_by_product)
    for p, s in shares.items():
        log.append(f"[전년] {p} 검사비율(점유)={s:.4%}")

    monthly_ratios = calc_inspection_production_ratio(prior_monthly_total_inspection, prior_prod)
    avg_ratio = calc_average_ratio(monthly_ratios, use_months=ratio_months)
    log.append(f"[전년] 월별 검사÷생산 비율 평균={avg_ratio:.6f}")

    monthly_forecast_total: list[float] = []
    monthly_forecast_by_product: dict[str, list[float]] = {p: [] for p in shares}
    annual_frequency = 0.0

    for m in range(months):
        month_total = forecast_prod[m] * avg_ratio
        monthly_forecast_total.append(month_total)
        month_sum = 0.0
        for product, share in shares.items():
            qty = month_total * share
            monthly_forecast_by_product[product].append(qty)
            month_sum += qty
        annual_frequency += month_sum
        log.append(
            f"[당해 {m + 1}월] 생산={forecast_prod[m]:,.0f} × 비율={avg_ratio:.6f} "
            f"→ 검사예상={month_sum:,.1f}"
        )

    log.append(f"[결과] 연간 발생빈도(검사예상 합계)={annual_frequency:,.2f}")

    factors = {
        "mode": "fg_style",
        "avg_inspection_ratio": avg_ratio,
        "product_shares": shares,
        "prior_annual_inspection_by_product": annual_by_product,
        "monthly_forecast_total": monthly_forecast_total,
        "monthly_forecast_by_product": monthly_forecast_by_product,
        "annual_frequency": annual_frequency,
        "ref_ratio": avg_ratio,
        "plan_qty": sum(forecast_prod),
    }
    return annual_frequency, factors, log
