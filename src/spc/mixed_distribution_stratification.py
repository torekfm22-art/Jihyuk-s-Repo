"""혼합분포 진단 · 공정 층화 · 분리 기준 추천 · 샘플 재구성."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from src.spc.decision_models import SpcDecisionResult
from src.spc.decision_service import SpcDecisionInput, SpcDecisionService
from src.spc.normality_transform import resolve_normality_transform, try_box_cox_transform, try_johnson_transform
from src.spc.qqplot_assessment import assess_qq_plot
from src.spc.sampler import SampleSelector
from src.spc.statistics import SpcAnalysisResult, SpcAnalyzer
from src.spc.stratified_subgroup_builder import reconstruct_stratified_subgroups

PpkCause = Literal[
    "산포 과다형",
    "중심 치우침형",
    "혼합분포형",
    "비정규형",
    "데이터 부족형",
    "정상",
]

STRAT_COLUMN_SPECS: list[tuple[str, str, tuple[str, ...]]] = [
    ("measurement_point", "측정호기", ("measurement_point", "네트 갯수", "값 갯수", "체결부위", "측정포인트")),
    ("shift", "교대", ("shift", "교대", "근무조", "작업조", "_strat_shift")),
    ("lot", "LOT", ("lot", "LOT", "로트번호", "로트 번호", "batch")),
    ("date", "날짜", ("measure_date", "측정일", "작업일", "_strat_date")),
    ("operator", "작업자", ("operator", "작업자", "worker", "작업자명")),
    ("machine", "설비", ("machine", "설비", "설비명", "설비번호", "equipment", "line")),
    ("line", "라인", ("line", "라인", "라인코드", "line_code")),
    ("process", "공정", ("process", "process_name", "공정", "공정명", "공정단계")),
    ("tool", "금형/치구", ("tool_id", "tool", "금형", "치구", "금형번호")),
    ("material_lot", "자재 LOT", ("material_lot", "자재lot", "자재 lot", "raw_material_lot")),
]

STRAT_EXCLUDE_EXACT: frozenset[str] = frozenset({
    "value", "usl", "lsl", "target", "subgroup_id", "original_index",
    "pp", "ppk", "cp", "cpk", "sampling_strategy", "sampling_boundary",
    "sampling_block", "sampling_date", "seq_start_index",
})
STRAT_DATE_COLUMNS: frozenset[str] = frozenset({
    "timestamp", "measure_date", "_strat_date",
})
MAX_STRAT_LEVELS = 30

COMBO_SIZE_MAX = 2

STANDARD_SINGLE_LOGICALS = ("measurement_point", "shift", "lot", "date")
STANDARD_PAIR_LOGICALS = (
    ("measurement_point", "shift"),
    ("measurement_point", "lot"),
    ("measurement_point", "date"),
    ("shift", "lot"),
    ("shift", "date"),
    ("lot", "date"),
)
FIXED_MP_PAIR_LOGICALS = (
    ("shift", "lot"),
    ("shift", "date"),
    ("lot", "date"),
)
EXTRA_SINGLE_LOGICALS = ("machine", "line", "operator")


@dataclass
class MixedDistributionDiagnosis:
    suspected: bool
    triggers: list[str] = field(default_factory=list)
    summary_message: str = ""
    shapiro_p: float = 1.0
    qq_r2: float | None = None
    boxcox_p: float | None = None
    johnson_p: float | None = None
    sigma_overall: float = 0.0
    sigma_within: float | None = None
    sigma_ratio: float | None = None
    ppk: float | None = None
    cpk: float | None = None
    ppk_cpk_gap: float | None = None
    histogram_multimodal: bool = False
    reference_only_ppk: bool = False


@dataclass
class GroupMetrics:
    group_key: str
    n: int
    subgroup_count: int
    mean: float
    median: float
    stdev_s: float
    stdev_p: float
    sigma_within: float | None
    sigma_ratio: float | None
    normality_p: float
    qq_r2: float | None
    is_normal: bool
    boxcox_p: float | None
    johnson_p: float | None
    pp: float | None
    ppk: float | None
    cp: float | None
    cpk: float | None
    ppk_cause: PpkCause
    rs_abnormal: bool
    xbar_abnormal: bool
    xbar_interpretation_deferred: bool
    interpretation_limited: bool
    action_hint: str = ""


@dataclass
class StratificationCandidateResult:
    rank: int
    split_basis: str
    split_columns: list[str]
    group_count: int
    min_n: int
    mean_n: float
    eta_squared: float
    overall_p: float
    mean_group_p: float
    normal_group_ratio: float
    overall_sigma_ratio: float | None
    mean_sigma_ratio: float | None
    min_ppk: float | None
    max_ppk: float | None
    rs_abnormal_groups: int
    xbar_abnormal_groups: int
    total_score: float
    recommended: bool
    summary: str
    mean_shift_range: float | None = None
    recommendation_judgment: str = ""
    rebuild_sigma_ratio: float | None = None
    subgroup_count_after: int = 0
    score_detail: str = ""
    groups: list[GroupMetrics] = field(default_factory=list)


@dataclass
class StratificationStudyResult:
    diagnosis: MixedDistributionDiagnosis
    overall: GroupMetrics
    candidates: list[StratificationCandidateResult]
    fixed_columns: list[str]
    available_columns: dict[str, str]
    recommended_basis: str | None
    narrative: list[str] = field(default_factory=list)


@dataclass
class StratifiedReanalysisResult:
    split_columns: list[str]
    before: GroupMetrics
    after_groups: list[GroupMetrics]
    sample_df: pd.DataFrame
    warnings: list[str]
    sampling_guidance: list[str]
    comparison_rows: list[dict[str, Any]]


def _prepare_strat_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "_strat_date" not in out.columns and "timestamp" in out.columns:
        ts = pd.to_datetime(out["timestamp"], errors="coerce")
        out["_strat_date"] = ts.dt.strftime("%Y-%m-%d")
    elif "_strat_date" not in out.columns and "measure_date" in out.columns:
        out["_strat_date"] = out["measure_date"].astype(str)
    if "shift" not in out.columns and "_strat_shift" not in out.columns and "timestamp" in out.columns:
        from src.spc.sampler import DAY_SHIFT_END_HOUR, DAY_SHIFT_START_HOUR

        ts = pd.to_datetime(out["timestamp"], errors="coerce")
        h = ts.dt.hour
        out["_strat_shift"] = "UNKNOWN"
        day_mask = ts.notna() & (h >= DAY_SHIFT_START_HOUR) & (h < DAY_SHIFT_END_HOUR)
        out.loc[day_mask, "_strat_shift"] = "주간"
        out.loc[ts.notna() & ~day_mask, "_strat_shift"] = "야간"
    return out


def _is_strat_skip_column(col: str) -> bool:
    if col in STRAT_EXCLUDE_EXACT:
        return True
    if str(col).lower().startswith("unnamed"):
        return True
    if str(col).startswith("sampling_"):
        return True
    if str(col).startswith("_") and col not in ("_strat_date", "_strat_shift"):
        return True
    return False


def _is_date_like_strat_column(col: str, df: pd.DataFrame) -> bool:
    if col in STRAT_DATE_COLUMNS:
        return True
    if col not in df.columns:
        return False
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        return True
    label = str(col)
    if any(k in label for k in ("일시", "날짜", "일자", "date", "time")):
        try:
            parsed = pd.to_datetime(df[col], errors="coerce")
            return bool(parsed.notna().mean() > 0.8)
        except Exception:
            pass
    return False


def _max_strat_levels(n_rows: int, subgroup_size: int = 5) -> int:
    return min(MAX_STRAT_LEVELS, max(2, n_rows // max(subgroup_size * 2, 1)))


def _series_has_measurement_precision(series: pd.Series) -> bool:
    """연속 측정치 패턴: 소수·넓은 범위·행마다 거의 다른 값."""
    num = pd.to_numeric(series, errors="coerce").dropna()
    if len(num) < 3:
        return False
    n = len(num)
    nuniq = int(num.nunique())
    if nuniq / n > 0.15:
        return True
    if (num - num.round()).abs().mean() > 1e-4:
        return True
    span = float(num.max() - num.min())
    if nuniq >= 3 and span > 1.0:
        return True
    return False


def _correlates_with_value(df: pd.DataFrame, col: str, value_col: str) -> bool:
    if value_col not in df.columns or col not in df.columns:
        return False
    val = pd.to_numeric(df[value_col], errors="coerce")
    other = pd.to_numeric(df[col], errors="coerce")
    mask = val.notna() & other.notna()
    if int(mask.sum()) < 10:
        return False
    corr = val[mask].corr(other[mask])
    return corr is not None and np.isfinite(corr) and abs(float(corr)) > 0.85


def classify_stratification_column(
    df: pd.DataFrame,
    col: str,
    *,
    value_col: str = "value",
    subgroup_size: int = 5,
    require_variation: bool = True,
) -> Literal["process", "date", "exclude"]:
    """
    공장·항목명과 무관하게 데이터 형태로 분리 기준 적합 여부 판별.
    - process: 범주형·저수준 코드 (교대·LOT·설비 등)
    - date: 일자·일시
    - exclude: 분석 대상 측정치·연속값·과다 수준·식별자
    """
    if not col or _is_strat_skip_column(col) or col == value_col:
        return "exclude"
    if col not in df.columns:
        return "exclude"

    if _is_date_like_strat_column(col, df):
        return "date"

    series = df[col].dropna()
    n = len(df)
    if len(series) < 2:
        return "exclude"
    nuniq = int(series.nunique())
    if require_variation and nuniq < 2:
        return "exclude"
    if nuniq > _max_strat_levels(n, subgroup_size):
        return "exclude"

    numeric_ratio = pd.to_numeric(series, errors="coerce").notna().mean()
    if numeric_ratio > 0.85:
        if _series_has_measurement_precision(series):
            return "exclude"
        if _correlates_with_value(df, col, value_col):
            return "exclude"
        return "process"

    if nuniq / max(len(series), 1) > 0.5:
        return "exclude"
    return "process"


def list_structural_stratification_columns(
    df: pd.DataFrame,
    *,
    value_col: str = "value",
    subgroup_size: int = 5,
) -> tuple[list[str], list[str]]:
    """(범주형 공정 조건 열, 날짜 열) — 항목명 화이트리스트 없이 형태로 탐지."""
    work = _prepare_strat_df(df)
    process_cols: list[str] = []
    date_cols: list[str] = []
    seen: set[str] = set()
    for col in work.columns:
        if col in seen:
            continue
        kind = classify_stratification_column(
            work, col, value_col=value_col, subgroup_size=subgroup_size,
        )
        if kind == "process":
            process_cols.append(col)
            seen.add(col)
        elif kind == "date":
            date_cols.append(col)
            seen.add(col)
    return process_cols, date_cols


def is_valid_stratification_split_column(
    df: pd.DataFrame,
    col: str,
    *,
    value_col: str = "value",
    subgroup_size: int = 5,
    require_variation: bool = True,
) -> bool:
    """공정·조건(범주형) 분리 기준만 허용."""
    return classify_stratification_column(
        df, col, value_col=value_col, subgroup_size=subgroup_size,
        require_variation=require_variation,
    ) in ("process", "date")


def _reasonable_strat_cardinality(
    df: pd.DataFrame,
    col: str,
    *,
    subgroup_size: int = 5,
) -> bool:
    return is_valid_stratification_split_column(df, col, subgroup_size=subgroup_size)


def resolve_stratification_columns(df: pd.DataFrame) -> dict[str, str]:
    found: dict[str, str] = {}
    work = _prepare_strat_df(df)
    col_keys = {str(c).strip().lower().replace(" ", ""): c for c in work.columns}
    for logical, _label, aliases in STRAT_COLUMN_SPECS:
        for alias in aliases:
            key = alias.strip().lower().replace(" ", "")
            if key in col_keys:
                found[logical] = col_keys[key]
                break
    return found


def build_split_candidates(
    df: pd.DataFrame,
    *,
    fixed_columns: list[str] | None = None,
    max_combo_size: int = COMBO_SIZE_MAX,
    subgroup_size: int = 5,
    value_col: str = "value",
) -> list[tuple[str, list[str]]]:
    """공정 조건 후보 — 항목명이 달라도 데이터 형태(범주·수준 수)로 자동 탐지."""
    _ = max_combo_size
    work = _prepare_strat_df(df)
    available = resolve_stratification_columns(work)
    process_cols, date_cols = list_structural_stratification_columns(
        work, value_col=value_col, subgroup_size=subgroup_size,
    )
    structural = list(dict.fromkeys(process_cols + date_cols))

    fixed = fixed_columns or []
    fixed_actual = [available[f] for f in fixed if f in available]
    variable_fixed = [
        c for c in fixed_actual
        if c in work.columns and work[c].nunique(dropna=True) >= 2
    ]
    mp_fixed = "measurement_point" in fixed

    col_to_label: dict[str, str] = {}
    for logical, label, _aliases in STRAT_COLUMN_SPECS:
        col = available.get(logical)
        if col and col in work.columns:
            col_to_label[col] = label
    for col in structural:
        col_to_label.setdefault(col, str(col))

    def _label_for_cols(cols: list[str]) -> str:
        return " + ".join(col_to_label.get(c, str(c)) for c in cols)

    def _split_columns(*variable: str) -> list[str]:
        if mp_fixed:
            return list(variable)
        out: list[str] = []
        seen: set[str] = set()
        for c in variable_fixed + list(variable):
            if c and c in work.columns and c not in seen:
                out.append(c)
                seen.add(c)
        return out

    def _append_combo(cols: list[str], out: list[tuple[str, list[str]]]) -> None:
        if not cols or not all(c in work.columns for c in cols):
            return
        for c in cols:
            if not is_valid_stratification_split_column(
                work, c, value_col=value_col, subgroup_size=subgroup_size,
            ):
                return
        basis = _label_for_cols(cols)
        if basis and (basis, cols) not in [(b, cs) for b, cs in out]:
            out.append((basis, cols))

    def _prioritized_singles() -> list[str]:
        order: list[str] = []
        logical_order = (
            ("shift", "lot", "date") if mp_fixed
            else STANDARD_SINGLE_LOGICALS
        )
        for key in logical_order:
            col = available.get(key)
            if col and col in structural and col not in order:
                order.append(col)
        for key in EXTRA_SINGLE_LOGICALS + ("process", "tool", "material_lot"):
            col = available.get(key)
            if col and col in structural and col not in order:
                order.append(col)
        for col in structural:
            if col not in order and col not in variable_fixed:
                order.append(col)
        return order

    combos: list[tuple[str, list[str]]] = []
    singles = _prioritized_singles()
    for col in singles:
        if col in variable_fixed:
            continue
        _append_combo(_split_columns(col), combos)

    pair_specs = FIXED_MP_PAIR_LOGICALS if mp_fixed else STANDARD_PAIR_LOGICALS
    for logical_a, logical_b in pair_specs:
        if logical_a in fixed or logical_b in fixed:
            continue
        ca, cb = available.get(logical_a), available.get(logical_b)
        if not ca or not cb:
            continue
        if ca not in structural or cb not in structural:
            continue
        _append_combo(_split_columns(ca, cb), combos)

    # 공장별 비표준 항목명 2개 조합 (우선순위 열 상위 6개 이내)
    extra_cols = [c for c in singles[:6] if c not in variable_fixed]
    for i, ca in enumerate(extra_cols):
        for cb in extra_cols[i + 1 :]:
            if (ca, cb) in [(cs[0], cs[1]) for _, cs in combos if len(cs) == 2]:
                continue
            if (cb, ca) in [(cs[0], cs[1]) for _, cs in combos if len(cs) == 2]:
                continue
            _append_combo(_split_columns(ca, cb), combos)

    return combos


def _adaptive_min_subgroup_count(
    df: pd.DataFrame,
    subgroup_size: int,
    requested: int = 25,
) -> int:
    n = len(df)
    if n < subgroup_size * 2:
        return 2
    max_sg = max(2, n // subgroup_size - 1)
    return min(requested, max(2, max_sg))


def _evaluate_candidate_with_rebuild(
    df: pd.DataFrame,
    cols: list[str],
    basis: str,
    overall_baseline: GroupMetrics,
    *,
    usl: float | None,
    lsl: float | None,
    subgroup_size: int,
    population_std: bool,
    min_subgroup_count: int,
) -> StratificationCandidateResult | None:
    """재구성 subgroup 후 지표·점수 산출 (추천 순위용)."""
    try:
        sample_df, _ = reconstruct_stratified_subgroups(
            df,
            cols,
            subgroup_size=subgroup_size,
            min_subgroup_count=2,
            incomplete_policy="keep_with_warning",
        )
    except Exception:
        return None
    if sample_df.empty or "subgroup_id" not in sample_df.columns:
        return None

    group_col = "split_key" if "split_key" in sample_df.columns else "strat_group_key"
    if group_col not in sample_df.columns:
        return None

    sg_count = int(sample_df["subgroup_id"].nunique())
    overall_after = analyze_group_slice(
        sample_df,
        group_key="전체(재구성)",
        usl=usl,
        lsl=lsl,
        subgroup_size=subgroup_size,
        population_std=population_std,
        min_subgroup_count=min_subgroup_count,
    )
    groups: list[GroupMetrics] = []
    for gkey, grp in sample_df.groupby(group_col, sort=False):
        groups.append(
            analyze_group_slice(
                grp,
                group_key=str(gkey),
                usl=usl,
                lsl=lsl,
                subgroup_size=subgroup_size,
                population_std=population_std,
                min_subgroup_count=2,
            )
        )
    if not groups:
        return None

    n_rows = len(df)
    if len(groups) > min(MAX_STRAT_LEVELS, max(2, n_rows // max(subgroup_size * 2, 1))):
        return None
    if all(g.n < subgroup_size for g in groups):
        return None

    score, summ, mean_range, judgment = _score_candidate(overall_after, groups, basis)
    bonus = 0.0
    bonus_notes: list[str] = []
    if (
        overall_baseline.sigma_ratio is not None
        and overall_after.sigma_ratio is not None
        and overall_baseline.sigma_ratio > 0
        and overall_after.sigma_ratio < overall_baseline.sigma_ratio * 0.9
    ):
        bonus += 10.0
        bonus_notes.append("σratio 개선")
    if overall_baseline.normality_p < 0.05:
        normal_cnt = sum(1 for g in groups if g.is_normal)
        if normal_cnt > 0:
            bonus += min(10.0, float(normal_cnt) * 4.0)
            bonus_notes.append(f"정규 {normal_cnt}그룹")

    total = min(100.0, score + bonus)
    if bonus > 0:
        summ = f"{summ}; +{bonus:.0f}점 ({', '.join(bonus_notes)})"
    judgment = _recommendation_judgment(basis, total)

    ns = [g.n for g in groups]
    ppks = [g.ppk for g in groups if g.ppk is not None and np.isfinite(g.ppk)]
    sr_vals = [g.sigma_ratio for g in groups if g.sigma_ratio is not None]

    return StratificationCandidateResult(
        rank=0,
        split_basis=basis,
        split_columns=cols,
        group_count=len(groups),
        min_n=min(ns) if ns else 0,
        mean_n=float(np.mean(ns)) if ns else 0.0,
        eta_squared=0.0,
        overall_p=overall_baseline.normality_p,
        mean_group_p=float(np.mean([g.normality_p for g in groups])) if groups else 0.0,
        normal_group_ratio=sum(1 for g in groups if g.is_normal) / len(groups) if groups else 0.0,
        overall_sigma_ratio=overall_baseline.sigma_ratio,
        mean_sigma_ratio=float(np.mean(sr_vals)) if sr_vals else overall_after.sigma_ratio,
        min_ppk=min(ppks) if ppks else None,
        max_ppk=max(ppks) if ppks else None,
        rs_abnormal_groups=sum(1 for g in groups if g.rs_abnormal),
        xbar_abnormal_groups=sum(1 for g in groups if g.xbar_abnormal),
        total_score=total,
        recommended=False,
        summary=summ,
        groups=groups,
        mean_shift_range=mean_range,
        recommendation_judgment=judgment,
        rebuild_sigma_ratio=overall_after.sigma_ratio,
        subgroup_count_after=sg_count,
        score_detail=summ,
    )


def _eta_squared(values: np.ndarray, labels: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels)
    mask = np.isfinite(values)
    values, labels = values[mask], labels[mask]
    if len(values) < 3 or len(np.unique(labels)) < 2:
        return 0.0
    grand = float(np.mean(values))
    ss_total = float(np.sum((values - grand) ** 2))
    if ss_total <= 0:
        return 0.0
    ss_between = 0.0
    for lab in np.unique(labels):
        grp = values[labels == lab]
        ss_between += len(grp) * (float(np.mean(grp)) - grand) ** 2
    return float(np.clip(ss_between / ss_total, 0.0, 1.0))


def _histogram_multimodal(values: np.ndarray) -> bool:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 8:
        return False
    n_uniq = len(np.unique(np.round(x, 2)))
    if n_uniq <= max(4, len(x) // 8):
        return True
    counts, _ = np.histogram(x, bins=min(15, max(5, len(x) // 5)))
    peaks = sum(
        1 for i in range(1, len(counts) - 1)
        if counts[i] > counts[i - 1] and counts[i] > counts[i + 1] and counts[i] > 0
    )
    return peaks >= 2


def _classify_ppk_cause(
    *,
    ppk: float | None,
    cp: float | None,
    pp: float | None,
    sigma_ratio: float | None,
    is_normal: bool,
    n: int,
    subgroup_count: int,
) -> PpkCause:
    if n < 10 or subgroup_count < 2:
        return "데이터 부족형"
    if not is_normal:
        return "비정규형"
    if sigma_ratio is not None and sigma_ratio > 1.3:
        return "혼합분포형"
    if ppk is not None and cp is not None and pp is not None:
        if cp >= 1.0 and pp >= 1.0 and ppk < 1.0:
            return "중심 치우침형"
        if cp < 1.0 or pp < 1.0:
            return "산포 과다형"
    return "정상"


def _sigma_within_from_df(df: pd.DataFrame, *, subgroup_size: int, analyzer: SpcAnalyzer) -> float | None:
    if "subgroup_id" not in df.columns or df["subgroup_id"].nunique() < 2:
        return None
    try:
        sub = SampleSelector.to_subgroup_matrix(df, subgroup_size)
        return float(analyzer.xbar_s_limits(sub).sigma_estimate)
    except Exception:
        return None


def analyze_group_slice(
    df: pd.DataFrame,
    *,
    group_key: str,
    usl: float | None,
    lsl: float | None,
    subgroup_size: int = 5,
    alpha: float = 0.05,
    population_std: bool = False,
    min_subgroup_count: int = 25,
) -> GroupMetrics:
    analyzer = SpcAnalyzer(alpha=alpha, population_std=population_std)
    values = pd.to_numeric(df["value"], errors="coerce").dropna().to_numpy(dtype=float)
    n = len(values)
    empty = GroupMetrics(
        group_key=group_key, n=n, subgroup_count=0, mean=0.0, median=0.0,
        stdev_s=0.0, stdev_p=0.0, sigma_within=None, sigma_ratio=None,
        normality_p=1.0, qq_r2=None, is_normal=False, boxcox_p=None, johnson_p=None,
        pp=None, ppk=None, cp=None, cpk=None, ppk_cause="데이터 부족형",
        rs_abnormal=False, xbar_abnormal=False, xbar_interpretation_deferred=False,
        interpretation_limited=True, action_hint="표본 부족",
    )
    if n < 2:
        return empty

    norm = analyzer.test_normality(values)
    qq = assess_qq_plot(values)
    stdev_s = float(np.std(values, ddof=1))
    stdev_p = float(np.std(values, ddof=0))
    sg_count = int(df["subgroup_id"].nunique()) if "subgroup_id" in df.columns else max(1, n // subgroup_size)
    sigma_w = _sigma_within_from_df(df, subgroup_size=subgroup_size, analyzer=analyzer)
    sigma_ratio = (stdev_s / sigma_w) if sigma_w and sigma_w > 0 else None

    bc = try_box_cox_transform(values, usl, lsl)
    jn = try_johnson_transform(values, usl, lsl) if bc is None or not bc.applied else None
    boxcox_p = bc.normality_after.p_value if bc and bc.normality_after else None
    johnson_p = jn.normality_after.p_value if jn and jn.normality_after else None

    cap = None
    rs_abnormal = False
    xbar_abnormal = False
    deferred = False

    if sg_count >= 2 and "subgroup_id" in df.columns:
        try:
            sub = SampleSelector.to_subgroup_matrix(df, subgroup_size)
            analysis = analyzer.analyze_xbar_s(sub, usl=usl, lsl=lsl)
            cap = analysis.capability
            decision = SpcDecisionService().evaluate(
                SpcDecisionInput(
                    analysis=analysis, raw_data=values, usl=usl, lsl=lsl,
                    subgroup_size=subgroup_size, sample_df=df,
                )
            )
            cc = decision.control_chart
            company = cc.company_interpretation
            rs_abnormal = bool(company and company.dispersion_abnormal)
            deferred = bool(company and company.mean_chart_deferred) or rs_abnormal
            xbar_abnormal = not cc.is_stable and not rs_abnormal
        except Exception:
            cap = analyzer.capability(values, usl=usl, lsl=lsl, sigma_within=sigma_w or stdev_s)
    else:
        cap = analyzer.capability(values, usl=usl, lsl=lsl, sigma_within=sigma_w or stdev_s)

    ppk = cap.ppk if cap else None
    cause = _classify_ppk_cause(
        ppk=ppk, cp=cap.cp if cap else None, pp=cap.pp if cap else None,
        sigma_ratio=sigma_ratio, is_normal=norm.is_normal, n=n, subgroup_count=sg_count,
    )
    limited = sg_count < min_subgroup_count or n < subgroup_size * 2
    hint = ""
    if deferred:
        hint = (
            "산포 관리도 이상 → 평균관리도 해석 보류. "
            "산포 원인 제거 후 Xbar·공정능력 재평가."
        )
    elif cause == "혼합분포형":
        hint = "조건별 층화 또는 샘플 재채취 필요"
    elif not norm.is_normal:
        hint = "Ppk 참고값 — 조건별 분리 또는 비정규 평가"

    return GroupMetrics(
        group_key=group_key, n=n, subgroup_count=sg_count,
        mean=float(np.mean(values)), median=float(np.median(values)),
        stdev_s=stdev_s, stdev_p=stdev_p, sigma_within=sigma_w, sigma_ratio=sigma_ratio,
        normality_p=float(norm.p_value), qq_r2=qq.fit_r2, is_normal=norm.is_normal,
        boxcox_p=boxcox_p, johnson_p=johnson_p,
        pp=cap.pp if cap else None, ppk=ppk, cp=cap.cp if cap else None, cpk=cap.cpk if cap else None,
        ppk_cause=cause, rs_abnormal=rs_abnormal, xbar_abnormal=xbar_abnormal,
        xbar_interpretation_deferred=deferred, interpretation_limited=limited, action_hint=hint,
    )


def diagnose_mixed_distribution(
    df: pd.DataFrame,
    *,
    usl: float | None,
    lsl: float | None,
    subgroup_size: int = 5,
    analysis: SpcAnalysisResult | None = None,
    alpha: float = 0.05,
) -> MixedDistributionDiagnosis:
    values = pd.to_numeric(df["value"], errors="coerce").dropna().to_numpy(dtype=float)
    analyzer = SpcAnalyzer(alpha=alpha)
    norm = analyzer.test_normality(values)
    qq = assess_qq_plot(values)

    sigma_w = None
    if analysis and analysis.control_limits:
        sigma_w = float(analysis.control_limits.sigma_estimate)
    elif "subgroup_id" in df.columns:
        sigma_w = _sigma_within_from_df(df, subgroup_size=subgroup_size, analyzer=analyzer)

    sigma_o = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    sigma_ratio = (sigma_o / sigma_w) if sigma_w and sigma_w > 0 else None

    transform = resolve_normality_transform(values, usl, lsl, chart_type="imr", subgroup_size=1)
    boxcox_p = johnson_p = None
    for att in transform.attempts:
        if att.get("method") == "box_cox":
            boxcox_p = att.get("p_value_after")
        if att.get("method") == "johnson_su":
            johnson_p = att.get("p_value_after")

    cap = analysis.capability if analysis else analyzer.capability(
        values, usl=usl, lsl=lsl, sigma_within=sigma_w or sigma_o
    )
    ppk = cap.ppk if cap else None
    cpk = cap.cpk if cap else None
    gap = abs(ppk - cpk) if ppk is not None and cpk is not None and np.isfinite(ppk) and np.isfinite(cpk) else None

    triggers: list[str] = []
    if norm.p_value < alpha:
        triggers.append("Shapiro p < 0.05")
    if qq.fit_r2 is not None and qq.fit_r2 < 0.95:
        triggers.append("QQ R² < 0.95")
    if boxcox_p is not None and boxcox_p < alpha:
        triggers.append("Box-Cox 후 p < 0.05")
    if johnson_p is not None and johnson_p < alpha:
        triggers.append("Johnson 후 p < 0.05")
    if sigma_ratio is not None and sigma_ratio > 1.3:
        triggers.append("σ_overall/σ_within > 1.3")
    if _histogram_multimodal(values):
        triggers.append("히스토그램 다봉/계단형")
    if gap is not None and ppk and ppk > 0 and gap / ppk > 0.25:
        triggers.append("Ppk-Cpk 차이 과다")

    transform_failed = (
        not norm.is_normal
        and (boxcox_p is None or boxcox_p < alpha)
        and (johnson_p is None or johnson_p < alpha)
    )
    suspected = len(triggers) >= 1
    reference_only = suspected and transform_failed

    summary = (
        "현재 데이터는 정규분포 가정을 만족하지 않으며 Box-Cox/Johnson 변환 후에도 "
        "정규성이 개선되지 않습니다. σ_overall/σ_within 비율이 크면 subgroup 간 평균 이동·"
        "조건별 혼합분포 가능성이 있습니다. 전체 Ppk는 참고값으로만 사용하고 "
        "공정 조건별 층화 분석이 필요합니다."
        if reference_only else (
            "혼합분포 또는 조건별 변동 가능성 — 공정 층화 분석을 권장합니다."
            if suspected else "단일 공정 분포 가능 — 층화 분석으로 확인하세요."
        )
    )

    return MixedDistributionDiagnosis(
        suspected=suspected, triggers=triggers, summary_message=summary,
        shapiro_p=float(norm.p_value), qq_r2=qq.fit_r2, boxcox_p=boxcox_p, johnson_p=johnson_p,
        sigma_overall=sigma_o, sigma_within=sigma_w, sigma_ratio=sigma_ratio,
        ppk=ppk, cpk=cpk, ppk_cpk_gap=gap,
        histogram_multimodal=_histogram_multimodal(values), reference_only_ppk=reference_only,
    )


def _sigma_ratio_score(avg_group_sigma_ratio: float | None) -> float:
    if avg_group_sigma_ratio is None:
        return 0.0
    if avg_group_sigma_ratio <= 1.2:
        return 30.0
    if avg_group_sigma_ratio <= 1.5:
        return 20.0
    if avg_group_sigma_ratio <= 2.0:
        return 10.0
    return 0.0


def _mean_shift_score(mean_shift_ratio: float) -> float:
    if mean_shift_ratio >= 1.0:
        return 25.0
    if mean_shift_ratio >= 0.7:
        return 20.0
    if mean_shift_ratio >= 0.4:
        return 10.0
    return 0.0


def _worst_case_score(overall_ppk: float | None, min_group_ppk: float | None) -> float:
    if (
        overall_ppk is not None
        and min_group_ppk is not None
        and np.isfinite(overall_ppk)
        and np.isfinite(min_group_ppk)
        and min_group_ppk < overall_ppk
    ):
        return 15.0
    return 5.0


def _recommendation_judgment(split_basis: str, total_score: float) -> str:
    primary = split_basis.split(" + ")[0].strip()
    if total_score >= 75:
        suffix = "가능성 높음"
    elif total_score >= 50:
        suffix = "일부 있음"
    else:
        suffix = "낮음"
    return f"{primary} 영향 {suffix}"


def _recommendation_narrative(best_basis: str, best: StratificationCandidateResult, overall_ppk: float | None) -> str:
    worst_ppk = best.min_ppk
    worst_grp = next((g for g in best.groups if g.ppk == worst_ppk), None)
    worst_name = worst_grp.group_key if worst_grp else "—"

    templates = {
        "교대": (
            "교대 기준으로 분리했을 때 정규성 및 sigma_ratio가 가장 크게 개선되었습니다. "
            "동일 호기 내 교대별 평균 또는 산포 차이가 혼합분포의 주요 원인일 가능성이 높습니다."
        ),
        "LOT": (
            "LOT 기준으로 분리했을 때 분포가 가장 안정적으로 개선되었습니다. "
            "특정 LOT 조건이 혼합분포 및 Ppk 저하의 주요 원인일 가능성이 높습니다."
        ),
        "날짜": (
            "날짜 기준으로 분리했을 때 평균 이동이 크게 확인되었습니다. "
            "시간 경과, 설비 조건 변화, Tool wear, 환경 변화 가능성을 확인해야 합니다."
        ),
        "측정호기": (
            "측정호기 기준으로 분리했을 때 그룹 간 차이가 가장 뚜렷합니다. "
            "호기별 공정 조건 차이가 혼합분포 원인일 가능성이 높습니다."
        ),
    }
    body = templates.get(best_basis.split(" + ")[0], (
        f"「{best_basis}」 기준으로 분리했을 때 개선 효과가 가장 큽니다. "
        "해당 조건의 조합 영향을 우선 점검하세요."
    ))
    if " + " in best_basis:
        body = (
            f"「{best_basis}」를 함께 고려했을 때 가장 좋은 개선 효과가 확인되었습니다. "
            "단일 조건보다 조합 영향이 큰 것으로 판단됩니다."
        )

    ppk_txt = f"{overall_ppk:.3f}" if overall_ppk is not None else "—"
    worst_txt = f"{worst_ppk:.3f}" if worst_ppk is not None else "—"
    return (
        f"혼합분포 원인 자동 분석 결과, **{best_basis}** 기준 분리가 1순위로 추천됩니다.\n\n"
        f"{body}\n\n"
        f"전체 Ppk={ppk_txt}, 분리 후 최저 Ppk={worst_txt} ({worst_name}).\n\n"
        f"아래 **「{best_basis} 기준으로 샘플 재구성」** 버튼을 눌러 subgroup을 다시 만드세요."
    )


def _score_candidate(overall: GroupMetrics, groups: list[GroupMetrics], split_basis: str) -> tuple[float, str, float | None, str]:
    if not groups:
        return 0.0, "유효 그룹 없음", None, "데이터 부족"

    norm_ratio = sum(1 for g in groups if g.is_normal) / len(groups)
    normality_score = norm_ratio * 30.0

    sr_vals = [g.sigma_ratio for g in groups if g.sigma_ratio is not None and np.isfinite(g.sigma_ratio)]
    avg_sr = float(np.mean(sr_vals)) if sr_vals else None
    sigma_ratio_score = _sigma_ratio_score(avg_sr)

    means = [g.mean for g in groups]
    mean_range = float(max(means) - min(means)) if means else 0.0
    overall_stdev = overall.stdev_s if overall.stdev_s and overall.stdev_s > 0 else 1e-9
    mean_shift_ratio = mean_range / overall_stdev
    mean_shift_score = _mean_shift_score(mean_shift_ratio)

    ppks = [g.ppk for g in groups if g.ppk is not None and np.isfinite(g.ppk)]
    min_ppk = min(ppks) if ppks else None
    worst_case_score = _worst_case_score(overall.ppk, min_ppk)

    total = normality_score + sigma_ratio_score + mean_shift_score + worst_case_score
    judgment = _recommendation_judgment(split_basis, total)
    summary = (
        f"정규 {norm_ratio:.0%}, σratio={avg_sr:.2f}" if avg_sr is not None else f"정규 {norm_ratio:.0%}"
    )
    return total, summary, mean_range, judgment


def run_stratification_study(
    filtered_df: pd.DataFrame,
    *,
    usl: float | None,
    lsl: float | None,
    subgroup_size: int = 5,
    min_subgroup_count: int = 25,
    fixed_columns: list[str] | None = None,
    analysis: SpcAnalysisResult | None = None,
    population_std: bool = False,
    sample_df: pd.DataFrame | None = None,
) -> StratificationStudyResult:
    df = _prepare_strat_df(filtered_df)
    if "value" not in df.columns:
        raise ValueError("value 열이 필요합니다.")

    effective_min_sg = _adaptive_min_subgroup_count(df, subgroup_size, min_subgroup_count)

    diagnosis = diagnose_mixed_distribution(
        df, usl=usl, lsl=lsl, subgroup_size=subgroup_size, analysis=analysis,
    )
    baseline_df = sample_df if (
        sample_df is not None
        and not sample_df.empty
        and "subgroup_id" in sample_df.columns
    ) else df
    overall = analyze_group_slice(
        baseline_df,
        group_key="현재 채취(전체)",
        usl=usl,
        lsl=lsl,
        subgroup_size=subgroup_size,
        population_std=population_std,
        min_subgroup_count=effective_min_sg,
    )

    available = resolve_stratification_columns(df)
    candidates_raw = build_split_candidates(
        df, fixed_columns=fixed_columns or [], subgroup_size=subgroup_size,
    )

    results: list[StratificationCandidateResult] = []
    for basis, cols in candidates_raw:
        for col in cols:
            if col not in df.columns:
                raise ValueError(f"선택한 분리 기준 컬럼 '{col}'이 데이터에 없습니다.")
        evaluated = _evaluate_candidate_with_rebuild(
            df,
            cols,
            basis,
            overall,
            usl=usl,
            lsl=lsl,
            subgroup_size=subgroup_size,
            population_std=population_std,
            min_subgroup_count=effective_min_sg,
        )
        if evaluated is not None:
            results.append(evaluated)

    results.sort(key=lambda r: r.total_score, reverse=True)
    for i, r in enumerate(results, 1):
        r.rank = i
        r.recommended = i == 1

    narrative: list[str] = []
    if results:
        narrative.append(
            _recommendation_narrative(
                results[0].split_basis, results[0], overall.ppk,
            )
        )
        narrative.append(
            (
                f"※ 추천 점수는 **공정 조건으로 subgroup 재구성 후** "
                f"정규성·σratio·Ppk 변화를 기준으로 계산했습니다. "
                f"분리 후보는 항목명이 아니라 **범주 수·데이터 형태**로 자동 선별하며, "
                f"분석 대상 측정치(`value`) 및 연속 수치 열은 제외됩니다. "
                f"(현재 채취 σratio={overall.sigma_ratio:.2f})"
            )
            if overall.sigma_ratio is not None
            else (
                "※ 추천 점수는 공정 조건 기준 subgroup 재구성 후 지표를 기준으로 계산합니다. "
                "후보는 데이터 형태로 자동 선별되며 측정치 열은 제외됩니다."
            )
        )
    elif not candidates_raw:
        narrative.append("분석 가능한 분리 기준(교대·LOT·날짜 등)이 데이터에 없습니다.")

    return StratificationStudyResult(
        diagnosis=diagnosis, overall=overall, candidates=results,
        fixed_columns=fixed_columns or [], available_columns=available,
        recommended_basis=results[0].split_basis if results else None, narrative=narrative,
    )


def _metrics_to_row(m: GroupMetrics, label: str) -> dict[str, Any]:
    return {
        "분석 단위": label, "n": m.n, "subgroup_count": m.subgroup_count, "mean": m.mean,
        "σ_overall": m.stdev_s, "σ_within": m.sigma_within, "sigma_ratio": m.sigma_ratio,
        "normality_p": m.normality_p, "QQ_R²": m.qq_r2, "Ppk": m.ppk, "Cpk": m.cpk,
        "R/S 이상": "Y" if m.rs_abnormal else "N", "Xbar 이상": "Y" if m.xbar_abnormal else "N",
        "해석 가능": "제한" if m.interpretation_limited else ("보류" if m.xbar_interpretation_deferred else "가능"),
        "조치 방향": m.action_hint or m.ppk_cause,
    }


def _build_sampling_guidance(split_columns: list[str], subgroup_size: int, min_subgroup_count: int) -> list[str]:
    return [
        f"분리 기준: {' + '.join(split_columns)}",
        f"동일 group_key 내 시간순 연속 {subgroup_size}개 = 1 subgroup",
        "교대·LOT·날짜 변경 시 subgroup 새로 시작",
        "서로 다른 group_key는 하나의 subgroup에 포함 금지",
        f"조건별 최소 {min_subgroup_count} subgroup 권장",
    ]


def run_stratified_reanalysis(
    filtered_df: pd.DataFrame,
    split_columns: list[str],
    *,
    usl: float | None,
    lsl: float | None,
    subgroup_size: int = 5,
    min_subgroup_count: int = 25,
    incomplete_policy: str = "keep_with_warning",
    population_std: bool = False,
) -> StratifiedReanalysisResult:
    df = _prepare_strat_df(filtered_df)
    for col in split_columns:
        if col not in df.columns:
            raise ValueError("선택한 분리 기준 컬럼이 데이터에 없습니다.")
    before = analyze_group_slice(
        df, group_key="분리 전(전체)", usl=usl, lsl=lsl, subgroup_size=subgroup_size,
        population_std=population_std, min_subgroup_count=min_subgroup_count,
    )
    sample_df, warnings = reconstruct_stratified_subgroups(
        df, split_columns, subgroup_size=subgroup_size,
        incomplete_policy=incomplete_policy,  # type: ignore[arg-type]
        min_subgroup_count=min_subgroup_count,
    )
    if "strat_group_key" in sample_df.columns and "split_key" not in sample_df.columns:
        sample_df = sample_df.rename(columns={"strat_group_key": "split_key"})
    if "strat_group_key" in sample_df.columns:
        sample_df = sample_df.drop(columns=["strat_group_key"])
    group_col = "split_key" if "split_key" in sample_df.columns else "strat_group_key"
    for gkey, grp in df.groupby(split_columns, dropna=False, sort=False):
        if len(grp) < subgroup_size:
            warnings.append("해당 그룹은 데이터 수가 부족하여 subgroup 생성이 제한됩니다.")
    sg_total = int(sample_df["subgroup_id"].nunique()) if "subgroup_id" in sample_df.columns else 0
    if sg_total < min_subgroup_count:
        warnings.append("관리도 해석 신뢰도가 낮습니다. 추가 데이터 수집이 필요합니다.")
    if before.sigma_within is not None and before.sigma_within <= 0:
        warnings.append("sigma_within 계산 불가: subgroup 내부 산포가 0이거나 데이터가 부족합니다.")
    after_groups = [
        analyze_group_slice(
            grp, group_key=str(gkey), usl=usl, lsl=lsl, subgroup_size=subgroup_size,
            population_std=population_std, min_subgroup_count=min_subgroup_count,
        )
        for gkey, grp in sample_df.groupby(group_col, sort=False)
    ]
    comparison = [_metrics_to_row(before, "분리 전")] + [_metrics_to_row(g, g.group_key) for g in after_groups]
    return StratifiedReanalysisResult(
        split_columns=split_columns, before=before, after_groups=after_groups,
        sample_df=sample_df, warnings=warnings,
        sampling_guidance=_build_sampling_guidance(split_columns, subgroup_size, min_subgroup_count),
        comparison_rows=comparison,
    )


def needs_mixed_distribution_rebuild(
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> bool:
    """비정규 + 변환 실패 시 혼합분포 재구성 섹션 표시."""
    if analysis.normality.is_normal:
        return False
    nd = decision.normality
    if nd.transform_success:
        return False
    return bool(nd.non_normal_detected or not analysis.normality.is_normal)


needs_stratification_analysis = needs_mixed_distribution_rebuild
