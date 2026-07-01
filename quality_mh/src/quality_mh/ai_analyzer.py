"""규칙 기반 M/H 자동 분석 (AI 분석 메뉴)."""
from __future__ import annotations

from quality_mh.models import CalcResult, QualitativeRecord
from quality_mh.plant_config import PlantConfig
from quality_mh.summary_engine import SummaryReport, build_summary_report, simulate_production_change


def analyze_top5_mh(calc_results: list[CalcResult]) -> list[dict]:
    items = sorted(calc_results, key=lambda x: x.standard_mh, reverse=True)[:5]
    total = sum(r.standard_mh for r in calc_results) or 1.0
    return [
        {
            "순위": i + 1,
            "업무": r.frequency_factors_used.get("task_name", r.record_id),
            "W/G": r.frequency_factors_used.get("wg", ""),
            "표준공수": round(r.standard_mh, 4),
            "표준인원": r.standard_headcount,
            "전체비중(%)": round(r.standard_mh / total * 100, 1),
        }
        for i, r in enumerate(items)
    ]


def analyze_headcount_impact(calc_results: list[CalcResult]) -> list[dict]:
    items = sorted(calc_results, key=lambda x: x.standard_headcount, reverse=True)[:5]
    return [
        {
            "순위": i + 1,
            "업무": r.frequency_factors_used.get("task_name", ""),
            "표준인원": r.standard_headcount,
            "표준공수": round(r.standard_mh, 4),
            "발생빈도": round(r.final_frequency, 2),
        }
        for i, r in enumerate(items)
    ]


def analyze_gap_causes(report: SummaryReport) -> list[str]:
    causes: list[str] = list(report.gap_comments)
    if not causes:
        causes.append("현재원과 표준인원의 차이가 허용 범위 내입니다.")
    for row in report.quantitative_rows:
        if row.sub_label in ("입고", "공정", "완성", "시험") and row.diff < -1:
            causes.append(
                f"▶ {row.sub_label}: 생산량 증가 또는 검사 강화로 표준인원 {abs(row.diff):.0f}명 추가 필요 가능"
            )
        if row.sub_label == "완성" and row.standard > row.current + 2:
            causes.append("▶ 완성품 검사 비중 증가 — 전수검사 모답스 단위시간 재검증 권장")
        if row.sub_label == "시험" and row.diff > 1:
            causes.append("▶ 시험업무 과다 배치 — 3차원 측정 모답스 분석 기준 대비 과다 인원 가능")
    return causes


def benchmark_plants(
    plant_reports: dict[str, SummaryReport],
) -> list[dict]:
    rows: list[dict] = []
    for plant, report in plant_reports.items():
        if report.total_row:
            rows.append({
                "공장": plant,
                "현재원": report.total_row.current,
                "표준인원": report.total_row.standard,
                "차이": report.total_row.diff,
                "근무시간": report.work_hours_per_day,
            })
    return rows


def full_analysis(
    config: PlantConfig,
    calc_results: list[CalcResult],
    qualitative: list[QualitativeRecord],
    production_change_pct: float = 10.0,
) -> dict:
    report = build_summary_report(config, calc_results, qualitative)
    return {
        "top5_mh": analyze_top5_mh(calc_results),
        "headcount_impact": analyze_headcount_impact(calc_results),
        "gap_causes": analyze_gap_causes(report),
        "simulation": simulate_production_change(config, calc_results, production_change_pct),
        "summary": report,
    }
