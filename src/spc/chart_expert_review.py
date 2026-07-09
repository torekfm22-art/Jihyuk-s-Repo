"""
차트별 품질 전문가 관점 점검·권고 (§20 Conclusions / Recommendations).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from src.spc.statistics import SpcAnalysisResult

CHART_LABELS = {
    "histogram": "11. Histogram (히스토그램)",
    "raw": "12. Raw Value Chart (개별값 시계열)",
    "npp": "13. Normal Probability Plot (정규확률도)",
    "control": "14. Control Chart (관리도)",
}


@dataclass
class ChartReviewSection:
    title: str
    status: str  # OK / 주의 / 조치
    watch_points: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


@dataclass
class ExpertChartReview:
    executive_summary: str
    sections: list[ChartReviewSection]
    priority_actions: list[str]

    def to_report_text(self) -> str:
        lines = [
            "【종합 판정】",
            self.executive_summary,
            "",
        ]
        for sec in self.sections:
            lines.append(f"■ {sec.title}  [{sec.status}]")
            if sec.watch_points:
                lines.append("  ※ 주의·해석")
                for p in sec.watch_points:
                    lines.append(f"    · {p}")
            if sec.checks:
                lines.append("  ※ 점검 항목")
                for c in sec.checks:
                    lines.append(f"    · {c}")
            if sec.actions:
                lines.append("  ※ 권고 조치")
                for a in sec.actions:
                    lines.append(f"    · {a}")
            lines.append("")
        if self.priority_actions:
            lines.append("■ 종합 우선 조치")
            for i, a in enumerate(self.priority_actions, 1):
                lines.append(f"  {i}. {a}")
        return "\n".join(lines).strip()


def _pct_outside_spec(
    data: np.ndarray,
    usl: float | None,
    lsl: float | None,
) -> tuple[float, float]:
    n = len(data)
    if n == 0:
        return 0.0, 0.0
    above = float(np.sum(data > usl) / n * 100) if usl is not None else 0.0
    below = float(np.sum(data < lsl) / n * 100) if lsl is not None else 0.0
    return above, below


def _npp_fit_r2(data: np.ndarray) -> float:
    x = np.sort(data.astype(float))
    n = len(x)
    if n < 3:
        return 0.0
    probs = (np.arange(1, n + 1) - 0.375) / (n + 0.25)
    theoretical = stats.norm.ppf(probs, loc=np.mean(x), scale=np.std(x, ddof=1))
    if np.std(theoretical) < 1e-12:
        return 0.0
    r = np.corrcoef(theoretical, x)[0, 1]
    return float(r * r)


def _raw_trend_slope(data: np.ndarray) -> float:
    if len(data) < 3:
        return 0.0
    x = np.arange(len(data), dtype=float)
    slope, _ = np.polyfit(x, data, 1)
    return float(slope)


def _count_dispersion_chart_ooc(result: SpcAnalysisResult) -> list[int]:
    """R/S/MR 차트 UCL 초과 subgroup·point."""
    cl = result.control_limits
    ooc: list[int] = []

    if result.chart_type == "imr" and result.individual_stats is not None and cl.mr_limits:
        df = result.individual_stats
        ucl = cl.mr_limits["UCL"]
        for i, v in enumerate(df["MR"].to_numpy()):
            if not np.isnan(v) and v > ucl:
                ooc.append(int(df["point"].iloc[i]))
        return ooc

    df = result.subgroup_stats
    if df is None:
        return ooc
    if result.chart_type == "xbar_r" and cl.r_limits and "R" in df.columns:
        ucl = cl.r_limits["UCL"]
        for i, v in enumerate(df["R"].to_numpy()):
            if v > ucl:
                ooc.append(int(df["subgroup"].iloc[i]))
    elif result.chart_type == "xbar_s" and cl.s_limits and "S" in df.columns:
        ucl = cl.s_limits["UCL"]
        for i, v in enumerate(df["S"].to_numpy()):
            if v > ucl:
                ooc.append(int(df["subgroup"].iloc[i]))
    return ooc


def _control_chart_title(result: SpcAnalysisResult) -> str:
    mapping = {
        "xbar_r": "Xbar-R Control Chart",
        "xbar_s": "Xbar-S Control Chart",
        "imr": "I-MR Control Chart",
    }
    return mapping.get(result.chart_type, "Control Chart")


def _review_histogram(result: SpcAnalysisResult, data: np.ndarray) -> ChartReviewSection:
    cap = result.capability
    norm = result.normality
    watch: list[str] = []
    checks: list[str] = []
    actions: list[str] = []
    status = "OK"

    if len(data) < 3:
        return ChartReviewSection(CHART_LABELS["histogram"], "주의", watch=["표본수 부족 — 분포 형상 판단 신뢰도 낮음"])

    skew = float(stats.skew(data, bias=False))
    kurt = float(stats.kurtosis(data, bias=False))
    if abs(skew) > 0.75:
        watch.append(f"분포 비대칭(skew={skew:.2f}) — 한쪽 꼬리·이상치·혼합 로트 가능성")
        status = "주의"
    if kurt > 1.5:
        watch.append(f"첨도 높음(kurtosis={kurt:.2f}) — 극단값·다봉 분포 검토")
        status = "주의"

    if cap:
        above, below = _pct_outside_spec(data, cap.usl, cap.lsl)
        if cap.usl is not None and cap.lsl is not None:
            spec_center = (cap.usl + cap.lsl) / 2
            offset = cap.mean - spec_center
            half = (cap.usl - cap.lsl) / 2
            if half > 0 and abs(offset) / half > 0.15:
                watch.append(
                    f"평균이 규격 중심 대비 {offset:+.4f} 이탈 — 히스토그램 피크가 USL/LSL 중 한쪽에 치우쳤는지 확인"
                )
                status = "주의"
        elif cap.usl is not None:
            margin = cap.usl - cap.mean
            if margin < 3 * cap.std_within:
                watch.append(
                    f"평균이 USL에 근접 (여유 {margin:.4f}) — 편측 상한 공차 중심 이탈 검토"
                )
                status = "주의"
        elif cap.lsl is not None:
            margin = cap.mean - cap.lsl
            if margin < 3 * cap.std_within:
                watch.append(
                    f"평균이 LSL에 근접 (여유 {margin:.4f}) — 편측 하한 공차 중심 이탈 검토"
                )
                status = "주의"
        if above > 0 or below > 0:
            watch.append(f"규격 이탈 표본 비율: USL 초과 {above:.2f}%, LSL 미만 {below:.2f}%")
            status = "조치" if (above + below) > 1 else "주의"
        if cap.cp > 0 and cap.cpk / cap.cp < 0.85:
            watch.append(
                f"Cp({cap.cp:.3f}) 대비 Cpk({cap.cpk:.3f}) 저하 — 변동은 충분하나 평균 위치(산포 중심) 불량 신호"
            )
            status = "주의"

    if not norm.is_normal:
        watch.append(
            f"정규성 미충족(p={norm.p_value:.4f}) — 히스토그램의 정규 곡선 오버레이는 참고용, Pp/Ppk 해석에 주의"
        )
        status = "주의" if status == "OK" else status

    checks.extend([
        "USL/LSL 대비 분포 폭·위치: 규격 내 집중 vs 양끝·한쪽 쏠림",
        "정규분포 곡선 대비 실제 막대: 꼬리 두께, 다봉(혼합 공정), 절단(측정 한계·반올림)",
        "히스토그램 bin 수에 따른 형상 왜곡 여부(표본수 대비 bin 과다/과소)",
        "평균선·규격한계와 피크 위치 일치 여부(목표값 대비 편향)",
    ])
    if status in ("주의", "조치"):
        actions.extend([
            "이상 구간 LOT·교대·설비·금형 등 메타데이터와 막대 구간 교차 확인",
            "비정규·다봉 시 로그/Box-Cox 변환 또는 비정규 공정능력 지표 병행 검토",
        ])
    if status == "조치":
        actions.append("규격 이탈 구간 원인분석(5Why)·임시조치·재측정으로 분포 재확인")

    return ChartReviewSection(CHART_LABELS["histogram"], status, watch, checks, actions)


def _review_raw_chart(result: SpcAnalysisResult, data: np.ndarray) -> ChartReviewSection:
    watch: list[str] = []
    checks: list[str] = []
    actions: list[str] = []
    status = "OK"

    if len(data) < 3:
        return ChartReviewSection(CHART_LABELS["raw"], "주의", watch=["연속 추세·이상점 패턴 판별에 표본 부족"])

    mean = float(np.mean(data))
    std = float(np.std(data, ddof=1)) if len(data) > 1 else 0.0
    slope = _raw_trend_slope(data)
    if std > 0:
        norm_slope = slope / std * len(data)
        if abs(norm_slope) > 0.5:
            direction = "상승" if slope > 0 else "하락"
            watch.append(f"순번 대비 {direction} 추세(기울기/σ 정규화≈{norm_slope:.2f}) — 공구 마모·온도·원료 등 시간 요인 의심")
            status = "주의"

    diffs = np.abs(np.diff(data))
    if len(diffs) > 0:
        jump_idx = int(np.argmax(diffs)) + 1
        if std > 0 and diffs.max() > 3 * std:
            watch.append(f"순번 {jump_idx} 부근 급격 변동(Δ={diffs.max():.4f}) — 셋업 변경·이상치·측정 오류 점검")
            status = "주의"

    if std > 0:
        out_3s = np.where(np.abs(data - mean) > 3 * std)[0] + 1
        if len(out_3s) > 0:
            pts = ", ".join(str(int(p)) for p in out_3s[:8])
            suffix = " …" if len(out_3s) > 8 else ""
            watch.append(f"평균±3σ 벗어난 순번: {pts}{suffix} (개별값 관점 이상 후보)")
            status = "주의"

    if result.out_of_control_points:
        pts = ", ".join(str(p) for p in result.out_of_control_points[:10])
        watch.append(f"관리도 기준 관리外 subgroup/포인트: {pts} — Raw 차트 동일 구간 연계 확인")
        status = "조치" if status != "조치" else status

    checks.extend([
        "시간·순번 방향 패턴: 상승/하락/주기(사이클)·계단 변화(조건 변경)",
        "단발 스파이크 vs 연속 밴드 이탈(특별원인 vs 공통원인 후보)",
        "측정 시스템·센서·영점 드리프트, 샘플링 누락/중복",
        "관리도 OOC 시점과 Raw 차트 위치 일치 여부",
    ])
    if status != "OK":
        actions.extend([
            "OOC·급변 순번의 작업조건·LOT·설비 이력과 교차 검증",
            "추세 지속 시 예방보전·공정 파라미터 재튜닝 후 재채취",
        ])

    return ChartReviewSection(CHART_LABELS["raw"], status, watch, checks, actions)


def _review_npp(result: SpcAnalysisResult, data: np.ndarray) -> ChartReviewSection:
    norm = result.normality
    r2 = _npp_fit_r2(data)
    watch: list[str] = []
    checks: list[str] = []
    actions: list[str] = []
    status = "OK"

    watch.append(f"Shapiro-Wilk p-value={norm.p_value:.4f} ({'정규' if norm.is_normal else '비정규'}), NPP 적합 R²≈{r2:.3f}")

    if r2 < 0.95 and norm.is_normal:
        watch.append("p-value는 정규이나 확률도 직선성 낮음 — 표본수·이상치·꼬리에서 미세 이탈 가능")
        status = "주의"
    if not norm.is_normal and r2 >= 0.97:
        watch.append("검정은 비정규이나 확률도는 거의 직선 — 중앙부만 정규·꼬리 이탈(heavy tail) 가능")
        status = "주의"
    if not norm.is_normal and r2 < 0.93:
        watch.append("비정규 + 직선성 저하 — 정규 가정 기반 Cp/Pp·PPM 해석 제한")
        status = "조치"

    checks.extend([
        "S자·곡선: 왜도 / 양 끝 동시 이탈: 첨도·이상치",
        "하단·상단 꼬리만 벗어남: 측정 한계·절단·혼합 집단",
        "이론 직선 대비 체계적 곡률: 변환(로그·Box-Cox) 필요 여부",
        "히스토그램·정규성 검정 결과와 삼각 교차 확인",
    ])
    if status != "OK":
        actions.extend([
            "꼬리 이탈 시 Winsorize/이상치 제거 전후 p-value·공정능력 비교",
            "비정규 확정 시 Johnson/분포 피팅 또는 비모수 규격 만족률 검토",
        ])

    return ChartReviewSection(CHART_LABELS["npp"], status, watch, checks, actions)


def _review_control_chart(result: SpcAnalysisResult) -> ChartReviewSection:
    title = f"14. {_control_chart_title(result)}"
    cl = result.control_limits
    watch: list[str] = []
    checks: list[str] = []
    actions: list[str] = []
    status = "OK"

    n_sg = cl.subgroup_size or 0
    xbar_ooc = result.out_of_control_points
    disp_ooc = _count_dispersion_chart_ooc(result)

    if xbar_ooc:
        pts = ", ".join(str(p) for p in xbar_ooc[:12])
        watch.append(f"Xbar(또는 I) 관리外: subgroup/point {pts} — 평균(위치) 특별원인 후보")
        status = "조치"
    if disp_ooc:
        pts = ", ".join(str(p) for p in disp_ooc[:12])
        label = {"xbar_r": "R", "xbar_s": "S", "imr": "MR"}.get(result.chart_type, "산포")
        watch.append(f"{label} 차트 UCL 초과: {pts} — 산포·변동 증가(공구·고정·원료) 후보")
        status = "조치"
    if not xbar_ooc and not disp_ooc:
        watch.append("관리한계 내 — 현 표본·기간 기준 통계적 관리 상태(특별원인 신호 없음)")

    if result.chart_type in ("xbar_r", "xbar_s"):
        checks.extend([
            f"Subgroup n={n_sg}: 부군 내 연속성·동일 LOT/조건 유지 여부(채취 규칙 준수)",
            "Xbar 이탈 + R/S 정상: 평균 이동(위치) / R·S 이탈 + Xbar 정상: 변동 증가 분리 해석",
            "Western Electric: 3σ 초과, 2σ 구간 2/3 연속, 7연속 증가·감소, 7연속 한쪽(규칙 1~4) 육안 점검",
            "R/S 하한(LCL) 근접: 측정 분해능·반올림·데이터 스택킹 의심",
        ])
    else:
        checks.extend([
            "I 차트: 개별값 특별원인, MR 차트: 인접 변동(이동범위) — MR UCL 초과 시 급변",
            "I-MR은 n=1 연속 데이터에 적합, subgroup 묶음 없을 때 해석",
            "자기상관·주기 패턴 시 I-MR 관리한계 과도 민감/둔감 여부 검토",
        ])

    if status == "조치":
        actions.extend([
            "OOC 발생 시점 전후 5W2H·변경점(4M1E) 기록, 조치 후 20~25 subgroup 재수집",
            "R/S만 OOC면 변동원인(고정·공구·환경), Xbar만 OOC면 평균·셋업·원료 배치 원인 우선",
        ])
    else:
        actions.append("현 상태 유지 시에도 정기적 관리도 갱신·관리한계 재계산(공정 변경 시)")

    return ChartReviewSection(title, status, watch, checks, actions)


def build_expert_chart_review(
    result: SpcAnalysisResult,
    raw_data: np.ndarray | None = None,
) -> ExpertChartReview:
    """분석 결과·원시 데이터 기반 차트별 전문가 리뷰."""
    data = np.asarray(raw_data, dtype=float) if raw_data is not None else np.array([])
    data = data[~np.isnan(data)] if len(data) else data

    sections = [
        _review_histogram(result, data) if len(data) else ChartReviewSection(
            CHART_LABELS["histogram"], "주의", watch=["측정값 데이터 없음"]
        ),
        _review_raw_chart(result, data) if len(data) else ChartReviewSection(
            CHART_LABELS["raw"], "주의", watch=["측정값 데이터 없음"]
        ),
        _review_npp(result, data) if len(data) else ChartReviewSection(
            CHART_LABELS["npp"], "주의", watch=["측정값 데이터 없음"]
        ),
        _review_control_chart(result),
    ]

    statuses = [s.status for s in sections]
    cap = result.capability
    priority: list[str] = []

    if "조치" in statuses or result.out_of_control_points:
        priority.append("관리도·Raw 차트 OOC 구간 원인분석 및 조치 후 재채취·재분석")
    if not result.normality.is_normal:
        priority.append("비정규 분포 — NPP·히스토그램 교차 확인 후 공정능력 지표 해석·대안 검토")
    if cap and cap.cpk < 1.0:
        priority.append(f"Cpk={cap.cpk:.3f} 미달 — 평균 위치·변동 원인 동시 개선(Statistical + Engineering)")
    elif cap and cap.cpk < 1.33:
        priority.append(f"Cpk={cap.cpk:.3f} — 고객/내부 목표(통상 1.33) 대비 여유 확보 검토")

    if not priority:
        priority.append("현 데이터 기준 특이 신호 없음 — 정기 모니터링·관리한계 유지")

    flags = []
    if result.out_of_control_points:
        flags.append("관리外")
    if not result.normality.is_normal:
        flags.append("비정규")
    if cap:
        if cap.cpk < 1.0:
            flags.append("Cpk 부족")
        elif cap.cpk >= 1.33:
            flags.append("Cpk 양호")
    flag_txt = ", ".join(flags) if flags else "특이 플래그 없음"

    executive = (
        f"4종 차트(히스토그램·Raw·정규확률도·{_control_chart_title(result)}) 통합 검토. "
        f"요약 플래그: {flag_txt}. "
        f"표본 n={result.normality.n}, 관리도={result.control_limits.chart_type}. "
        "아래는 차트별 주의·점검·권고입니다."
    )

    return ExpertChartReview(executive_summary=executive, sections=sections, priority_actions=priority)


def format_conclusions_for_report(
    result: SpcAnalysisResult,
    raw_data: np.ndarray | None = None,
) -> str:
    """§20 Conclusions / Recommendations 본문."""
    return build_expert_chart_review(result, raw_data).to_report_text()
