"""
SPC 통계 분석: 정규성 검정, 관리도 한계, 공정능력(Cp/Cpk).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import pandas as pd
from scipy import stats

from src.spc.constants import A2, A3, B3, B4, C4, D2, D3, D4, I_MR_D2, I_MR_D4

logger = logging.getLogger(__name__)

SpecType = Literal["two_sided", "upper_only", "lower_only"]


def infer_spec_type(usl: float | None, lsl: float | None) -> SpecType:
    """공차 유형 — 양측 / 상한만 / 하한만."""
    if usl is not None and lsl is not None:
        return "two_sided"
    if usl is not None:
        return "upper_only"
    if lsl is not None:
        return "lower_only"
    return "two_sided"


def _cap_nan() -> float:
    return float("nan")


def _cap_round(val: float, digits: int = 4) -> float | str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return round(val, digits)


@dataclass
class NormalityResult:
    test_name: str
    statistic: float
    p_value: float
    is_normal: bool
    alpha: float = 0.05
    n: int = 0

    def to_dict(self) -> dict:
        return {
            "검정방법": self.test_name,
            "통계량": round(self.statistic, 6),
            "p_value": round(self.p_value, 6),
            "정규성_판정": "정규" if self.is_normal else "비정규",
            "유의수준": self.alpha,
            "표본수": self.n,
        }


@dataclass
class ControlLimits:
    chart_type: str
    center_line: float
    ucl: float
    lcl: float
    sigma_estimate: float
    subgroup_size: Optional[int] = None
    xbar_limits: Optional[dict] = None
    r_limits: Optional[dict] = None
    s_limits: Optional[dict] = None
    i_limits: Optional[dict] = None
    mr_limits: Optional[dict] = None

    def to_dict(self) -> dict:
        base = {
            "관리도유형": self.chart_type,
            "중심선(CL)": round(self.center_line, 6),
            "UCL": round(self.ucl, 6),
            "LCL": round(self.lcl, 6),
            "추정σ(within)": round(self.sigma_estimate, 6),
        }
        if self.subgroup_size:
            base["subgroup크기"] = self.subgroup_size
        return base


@dataclass
class CapabilityResult:
    usl: float | None
    lsl: float | None
    mean: float
    std_within: float
    std_overall: float
    cp: float
    cpk: float
    pp: float
    ppk: float
    cpu: float
    cpl: float
    ppm_est: float
    spec_type: SpecType = "two_sided"

    def to_dict(self) -> dict:
        return {
            "USL": self.usl if self.usl is not None else "—",
            "LSL": self.lsl if self.lsl is not None else "—",
            "공차유형": self.spec_type,
            "평균(Xbar)": round(self.mean, 6),
            "σ_within": round(self.std_within, 6),
            "σ_overall": round(self.std_overall, 6),
            "Cp": _cap_round(self.cp),
            "Cpk": _cap_round(self.cpk),
            "Pp": _cap_round(self.pp),
            "Ppk": _cap_round(self.ppk),
            "Cpu/CWU": _cap_round(self.cpu),
            "Cpl/CWL": _cap_round(self.cpl),
            "예상PPM": round(self.ppm_est, 2),
        }


@dataclass
class SpcAnalysisResult:
    chart_type: Literal["xbar_s", "xbar_r", "imr"]
    normality: NormalityResult
    control_limits: ControlLimits
    capability: Optional[CapabilityResult]
    subgroup_stats: Optional[pd.DataFrame] = None
    individual_stats: Optional[pd.DataFrame] = None
    out_of_control_points: list[int] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class SpcAnalyzer:
    """정규성 → 관리도 → 공정능력 일괄 분석."""

    def __init__(self, alpha: float = 0.05, population_std: bool = False):
        self.alpha = alpha
        self.population_std = population_std

    def _analysis_metadata(self) -> dict:
        return {"population_std": self.population_std}

    def test_normality(self, data: np.ndarray) -> NormalityResult:
        data = np.asarray(data, dtype=float)
        data = data[~np.isnan(data)]
        n = len(data)

        if n < 3:
            return NormalityResult("Shapiro-Wilk", 0.0, 1.0, False, self.alpha, n)

        if n <= 5000:
            stat, p = stats.shapiro(data)
            name = "Shapiro-Wilk"
        else:
            stat, p = stats.normaltest(data)
            name = "D'Agostino-Pearson"

        return NormalityResult(name, float(stat), float(p), p >= self.alpha, self.alpha, n)

    def xbar_r_limits(self, subgroups: np.ndarray) -> ControlLimits:
        """X-bar R 관리도 한계."""
        n = subgroups.shape[1]
        if n not in A2:
            raise ValueError(f"subgroup 크기 {n}은 지원 범위(2~10) 밖입니다.")

        xbar = subgroups.mean(axis=1)
        r = subgroups.max(axis=1) - subgroups.min(axis=1)
        xbar_bar = xbar.mean()
        r_bar = r.mean()

        sigma = r_bar / D2[n]
        x_ucl = xbar_bar + A2[n] * r_bar
        x_lcl = xbar_bar - A2[n] * r_bar
        r_ucl = D4[n] * r_bar
        r_lcl = D3[n] * r_bar

        return ControlLimits(
            chart_type="X-bar R",
            center_line=xbar_bar,
            ucl=x_ucl,
            lcl=x_lcl,
            sigma_estimate=sigma,
            subgroup_size=n,
            xbar_limits={"CL": xbar_bar, "UCL": x_ucl, "LCL": x_lcl},
            r_limits={"CL": r_bar, "UCL": r_ucl, "LCL": r_lcl},
        )

    def xbar_s_limits(self, subgroups: np.ndarray) -> ControlLimits:
        """X-bar S 관리도 한계 (AIAG / Minitab)."""
        n = subgroups.shape[1]
        if n not in A3:
            raise ValueError(f"subgroup 크기 {n}은 지원 범위(2~10) 밖입니다.")

        xbar = subgroups.mean(axis=1)
        s_vals = subgroups.std(axis=1, ddof=1)
        xbar_bar = xbar.mean()
        s_bar = s_vals.mean()

        sigma = s_bar / C4[n]
        x_ucl = xbar_bar + A3[n] * s_bar
        x_lcl = xbar_bar - A3[n] * s_bar
        s_ucl = B4[n] * s_bar
        s_lcl = B3[n] * s_bar

        return ControlLimits(
            chart_type="X-bar S",
            center_line=xbar_bar,
            ucl=x_ucl,
            lcl=x_lcl,
            sigma_estimate=sigma,
            subgroup_size=n,
            xbar_limits={"CL": xbar_bar, "UCL": x_ucl, "LCL": x_lcl},
            s_limits={"CL": s_bar, "UCL": s_ucl, "LCL": s_lcl},
        )

    def imr_limits(self, individuals: np.ndarray) -> ControlLimits:
        """I-MR 관리도 한계."""
        x = np.asarray(individuals, dtype=float)
        mr = np.abs(np.diff(x))
        x_bar = x.mean()
        mr_bar = mr.mean() if len(mr) else 0.0

        sigma = mr_bar / I_MR_D2 if mr_bar else 0.0
        i_ucl = x_bar + 2.66 * mr_bar
        i_lcl = x_bar - 2.66 * mr_bar
        mr_ucl = I_MR_D4 * mr_bar

        return ControlLimits(
            chart_type="I-MR",
            center_line=x_bar,
            ucl=i_ucl,
            lcl=i_lcl,
            sigma_estimate=sigma,
            i_limits={"CL": x_bar, "UCL": i_ucl, "LCL": i_lcl},
            mr_limits={"CL": mr_bar, "UCL": mr_ucl, "LCL": 0.0},
        )

    def capability(
        self,
        data: np.ndarray,
        usl: float | None = None,
        lsl: float | None = None,
        sigma_within: float = 0,
    ) -> CapabilityResult:
        """
        공정능력 지표.

        - 양측: Cp/Cpk, Pp/Ppk (표준)
        - 상한만 (CWU): Cpk=Cpu=(USL−x̄)/(3σ_w), Ppk=Ppu
        - 하한만 (CWL): Cpk=Cpl=(x̄−LSL)/(3σ_w), Ppk=Ppl
        """
        spec_type = infer_spec_type(usl, lsl)
        data = np.asarray(data, dtype=float)
        mean = float(np.mean(data))
        ddof = 0 if self.population_std else 1
        std_overall = float(np.std(data, ddof=ddof)) if len(data) > 1 else 0.0
        std_w = sigma_within if sigma_within > 0 else std_overall

        nan = _cap_nan()
        if std_w <= 0:
            cp = cpk = pp = ppk = cpu = cpl = 0.0
            ppm = 0.0
        elif spec_type == "upper_only" and usl is not None:
            cpu = (usl - mean) / (3 * std_w)
            cpk = cpu
            cpl = nan
            cp = nan
            ppu = (usl - mean) / (3 * std_overall) if std_overall > 0 else 0.0
            ppk = ppu
            pp = nan
            z_usl = (usl - mean) / std_w
            ppm = float(stats.norm.sf(z_usl)) * 1_000_000
        elif spec_type == "lower_only" and lsl is not None:
            cpl = (mean - lsl) / (3 * std_w)
            cpk = cpl
            cpu = nan
            cp = nan
            ppl = (mean - lsl) / (3 * std_overall) if std_overall > 0 else 0.0
            ppk = ppl
            pp = nan
            z_lsl = (mean - lsl) / std_w
            ppm = float(stats.norm.cdf(-z_lsl)) * 1_000_000
        else:
            assert usl is not None and lsl is not None
            cp = (usl - lsl) / (6 * std_w)
            cpu = (usl - mean) / (3 * std_w)
            cpl = (mean - lsl) / (3 * std_w)
            cpk = min(cpu, cpl)
            pp = (usl - lsl) / (6 * std_overall) if std_overall > 0 else 0.0
            ppk = min(
                (usl - mean) / (3 * std_overall) if std_overall > 0 else 0.0,
                (mean - lsl) / (3 * std_overall) if std_overall > 0 else 0.0,
            )
            z_usl = (usl - mean) / std_w
            z_lsl = (mean - lsl) / std_w
            ppm = (stats.norm.sf(z_usl) + stats.norm.cdf(-z_lsl)) * 1_000_000

        return CapabilityResult(
            usl, lsl, mean, std_w, std_overall,
            cp, cpk, pp, ppk, cpu, cpl, ppm, spec_type,
        )

    def analyze_xbar_r(
        self,
        subgroups: np.ndarray,
        usl: Optional[float] = None,
        lsl: Optional[float] = None,
    ) -> SpcAnalysisResult:
        flat = subgroups.ravel()
        norm = self.test_normality(flat)
        limits = self.xbar_r_limits(subgroups)

        xbar = subgroups.mean(axis=1)
        r_vals = subgroups.max(axis=1) - subgroups.min(axis=1)
        subgroup_df = pd.DataFrame({
            "subgroup": np.arange(1, len(xbar) + 1),
            "Xbar": xbar,
            "R": r_vals,
        })

        ooc = [
            int(i + 1)
            for i, v in enumerate(xbar)
            if v > limits.xbar_limits["UCL"] or v < limits.xbar_limits["LCL"]
        ]

        cap = None
        if usl is not None or lsl is not None:
            cap = self.capability(flat, usl=usl, lsl=lsl, sigma_within=limits.sigma_estimate)

        return SpcAnalysisResult(
            chart_type="xbar_r",
            normality=norm,
            control_limits=limits,
            capability=cap,
            subgroup_stats=subgroup_df,
            out_of_control_points=ooc,
            metadata=self._analysis_metadata(),
        )

    def analyze_xbar_s(
        self,
        subgroups: np.ndarray,
        usl: Optional[float] = None,
        lsl: Optional[float] = None,
    ) -> SpcAnalysisResult:
        flat = subgroups.ravel()
        norm = self.test_normality(flat)
        limits = self.xbar_s_limits(subgroups)

        xbar = subgroups.mean(axis=1)
        s_vals = subgroups.std(axis=1, ddof=1)
        subgroup_df = pd.DataFrame({
            "subgroup": np.arange(1, len(xbar) + 1),
            "Xbar": xbar,
            "S": s_vals,
        })

        ooc = [
            int(i + 1)
            for i, v in enumerate(xbar)
            if v > limits.xbar_limits["UCL"] or v < limits.xbar_limits["LCL"]
        ]

        cap = None
        if usl is not None or lsl is not None:
            cap = self.capability(flat, usl=usl, lsl=lsl, sigma_within=limits.sigma_estimate)

        return SpcAnalysisResult(
            chart_type="xbar_s",
            normality=norm,
            control_limits=limits,
            capability=cap,
            subgroup_stats=subgroup_df,
            out_of_control_points=ooc,
            metadata=self._analysis_metadata(),
        )

    def analyze_imr(
        self,
        individuals: np.ndarray,
        usl: Optional[float] = None,
        lsl: Optional[float] = None,
    ) -> SpcAnalysisResult:
        x = np.asarray(individuals, dtype=float)
        norm = self.test_normality(x)
        limits = self.imr_limits(x)

        mr = np.concatenate([[np.nan], np.abs(np.diff(x))])
        ind_df = pd.DataFrame({"point": np.arange(1, len(x) + 1), "I": x, "MR": mr})

        ooc = [
            int(i + 1)
            for i, v in enumerate(x)
            if v > limits.i_limits["UCL"] or v < limits.i_limits["LCL"]
        ]

        cap = None
        if usl is not None or lsl is not None:
            cap = self.capability(x, usl=usl, lsl=lsl, sigma_within=limits.sigma_estimate)

        return SpcAnalysisResult(
            chart_type="imr",
            normality=norm,
            control_limits=limits,
            capability=cap,
            individual_stats=ind_df,
            out_of_control_points=ooc,
            metadata=self._analysis_metadata(),
        )
