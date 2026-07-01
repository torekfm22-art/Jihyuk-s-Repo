"""M/H 분석 결과(종합) 집계 엔진."""
from __future__ import annotations

from dataclasses import dataclass, field

from quality_mh.calculation_engine import round_headcount
from quality_mh.models import CalcResult, QualitativeRecord, RoundingPolicy
from quality_mh.plant_config import PlantConfig, WG_CATEGORIES

QUANT_WG = ["입고", "공정", "완성", "시험", "공통"]


@dataclass
class WgSummaryRow:
    category: str
    sub_label: str
    current: float
    standard: float
    diff: float
    comment: str = ""


@dataclass
class SummaryReport:
    plant: str
    year: int
    work_hours_per_day: float
    annual_available_hours: float
    allowance_rate: float
    quantitative_rows: list[WgSummaryRow] = field(default_factory=list)
    qualitative_row: WgSummaryRow | None = None
    non_standard_rows: list[WgSummaryRow] = field(default_factory=list)
    total_row: WgSummaryRow | None = None
    gap_comments: list[str] = field(default_factory=list)
    pareto: list[dict] = field(default_factory=list)


def _wg_from_result(r: CalcResult) -> str:
    return str(r.frequency_factors_used.get("wg", "공통"))


def build_summary_report(
    config: PlantConfig,
    calc_results: list[CalcResult],
    qualitative: list[QualitativeRecord],
) -> SummaryReport:
    """엑셀 종합 시트와 동일 구조의 요약 리포트 생성."""
    policy = config.effective_rounding_policy()
    wg_mh: dict[str, float] = {w: 0.0 for w in QUANT_WG}
    wg_hc_raw: dict[str, float] = {w: 0.0 for w in QUANT_WG}

    for r in calc_results:
        wg = _wg_from_result(r)
        if wg not in wg_mh:
            wg_mh[wg] = 0.0
            wg_hc_raw[wg] = 0.0
        wg_mh[wg] += r.standard_mh
        wg_hc_raw[wg] += r.standard_headcount

    quant_rows: list[WgSummaryRow] = []
    quant_current_sum = 0.0
    quant_std_sum = 0.0
    for wg in ["입고", "공정", "완성", "시험"]:
        cur = config.current_headcount.get(wg, 0.0)
        std = wg_hc_raw.get(wg, 0.0)
        diff = cur - std
        comment = ""
        if diff < -0.5:
            comment = f"{wg}검사 인원 부족 (표준 대비 {abs(diff):.1f}명 부족)"
        elif diff > 0.5:
            comment = f"{wg} 영역 인원 과다 (표준 대비 {diff:.1f}명 초과)"
        quant_rows.append(WgSummaryRow("표준", wg, cur, std, diff, comment))
        quant_current_sum += cur
        quant_std_sum += std

    quant_rows.append(
        WgSummaryRow("표준", "合", quant_current_sum, quant_std_sum,
                     quant_current_sum - quant_std_sum)
    )

    qual_std = sum(r.standard_headcount for r in qualitative)
    qual_cur = config.current_headcount.get("정성", qual_std)
    qual_row = WgSummaryRow("표준", "정 성 合", qual_cur, float(qual_std), qual_cur - qual_std)

    sub_current = quant_current_sum + qual_cur
    sub_standard = quant_std_sum + qual_std
    subtotal = WgSummaryRow("표준", "소 계", sub_current, sub_standard, sub_current - sub_standard)

    ns_rows: list[WgSummaryRow] = []
    ns_cur = 0.0
    ns_std = 0.0
    for label in ("그룹장", "파트장", "지원조"):
        cur = config.non_standard_headcount.get(label, 0.0)
        std = cur
        ns_rows.append(WgSummaryRow("표준外", label, cur, std, 0.0))
        ns_cur += cur
        ns_std += std
    ns_rows.append(WgSummaryRow("표준外", "合", ns_cur, ns_std, 0.0))

    total = WgSummaryRow(
        "표준外", "총 계",
        sub_current + ns_cur,
        sub_standard + ns_std,
        (sub_current + ns_cur) - (sub_standard + ns_std),
    )

    gap_comments: list[str] = []
    for row in quant_rows:
        if row.comment:
            gap_comments.append(row.comment)
    if qual_row.diff < -0.5:
        gap_comments.append("정성 업무 인원 부족")
    elif qual_row.diff > 0.5:
        gap_comments.append("정성 업무 인원 과다 배치")
    if sub_standard - sub_current > 3:
        gap_comments.append("전체적으로 표준인원 대비 현재원 부족 → 채용/전배 검토 필요")
    elif sub_current - sub_standard > 3:
        gap_comments.append("전체적으로 표준인원 대비 현재원 과다 → 업무 재배치 검토 필요")

    # Pareto TOP10
    pareto_items = sorted(calc_results, key=lambda x: x.standard_mh, reverse=True)[:10]
    total_mh = sum(r.standard_mh for r in calc_results) or 1.0
    pareto = [
        {
            "업무": r.frequency_factors_used.get("task_name", r.record_id),
            "W/G": _wg_from_result(r),
            "표준공수": round(r.standard_mh, 4),
            "비중(%)": round(r.standard_mh / total_mh * 100, 1),
            "표준인원": r.standard_headcount,
        }
        for r in pareto_items
    ]

    return SummaryReport(
        plant=config.plant_name,
        year=config.analysis_year,
        work_hours_per_day=config.work_hours_per_day,
        annual_available_hours=config.work_hours_per_year,
        allowance_rate=config.allowance_rate,
        quantitative_rows=quant_rows,
        qualitative_row=qual_row,
        non_standard_rows=ns_rows,
        total_row=total,
        gap_comments=gap_comments,
        pareto=pareto,
    )


def simulate_production_change(
    config: PlantConfig,
    calc_results: list[CalcResult],
    change_pct: float,
) -> dict:
    """생산량 변화 시뮬레이션 (+/- %)."""
    factor = 1 + change_pct / 100
    adjusted_mh = 0.0
    adjusted_hc = 0
    details: list[dict] = []
    policy = config.effective_rounding_policy()

    for r in calc_results:
        method = r.frequency_method_used.value if r.frequency_method_used else ""
        if "생산" in method or "연동" in method:
            new_mh = r.standard_mh * factor
            new_hc, _, _ = round_headcount(new_mh, policy)
            adjusted_mh += new_mh
            adjusted_hc += new_hc
            details.append({
                "업무": r.frequency_factors_used.get("task_name", ""),
                "현재M/H": r.standard_mh,
                "시뮬M/H": round(new_mh, 4),
                "현재인원": r.standard_headcount,
                "시뮬인원": new_hc,
            })
        else:
            adjusted_mh += r.standard_mh
            adjusted_hc += r.standard_headcount

    base_mh = sum(r.standard_mh for r in calc_results)
    base_hc = sum(r.standard_headcount for r in calc_results)
    return {
        "change_pct": change_pct,
        "base_mh": round(base_mh, 4),
        "simulated_mh": round(adjusted_mh, 4),
        "base_headcount": base_hc,
        "simulated_headcount": adjusted_hc,
        "delta_headcount": adjusted_hc - base_hc,
        "details": details,
    }
